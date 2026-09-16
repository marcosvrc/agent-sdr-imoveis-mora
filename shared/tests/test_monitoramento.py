"""Observabilidade leve (ADR-0011).

O ponto destes testes não é "a função roda": é que ela não pode derrubar o atendimento nem mentir.
Duas propriedades importam — escrita best-effort (banco fora do ar não estoura o turno) e detecção
de serviço parado (o sintoma que ninguém viu quando o worker do Ollama caiu).
"""
import os

os.environ.setdefault("SDR_DATABASE_DSN", "postgresql://sdr:sdr@localhost:5433/sdr_test")
from sdr_shared.db.guarda_teste import exigir_banco_de_teste; exigir_banco_de_teste()  # noqa: E402
os.environ["SDR_PROFILE"] = "local"

from sdr_shared.db import get_pool                                    # noqa: E402
from sdr_shared.db import monitoramento as mon                        # noqa: E402


def setup_function(_):
    with get_pool().connection() as c:
        for t in ("turnos", "saude", "batimentos"):
            c.execute(f"DELETE FROM {t}")


def test_resumo_calcula_percentis_e_taxa_de_falha():
    for ms in (100, 200, 300, 40_000):
        mon.registrar_turno(lead_id="l1", canal="web", resultado="ok", duracao_ms=ms, estagio="novo", nos=["supervisor"])
    mon.registrar_turno(lead_id="l1", canal="web", resultado="erro", duracao_ms=500)

    r = mon.resumo_de_turnos(horas=1)
    assert r["total"] == 5
    assert r["p50_ms"] == 300 and r["p95_ms"] == 40_000
    assert r["pior_ms"] == 40_000 and r["acima_de_30s"] == 1
    assert r["taxa_falha"] == 20.0, "1 de 5 turnos não terminou em ok"
    assert r["por_resultado"] == {"ok": 4, "erro": 1}
    assert len(r["serie"]) == 1 and r["serie"][0]["falhas"] == 1


def test_resumo_sem_turnos_nao_divide_por_zero():
    r = mon.resumo_de_turnos(horas=1)
    assert r == {"total": 0, "p50_ms": 0, "p95_ms": 0, "pior_ms": 0, "taxa_falha": 0.0,
                 "acima_de_30s": 0, "por_resultado": {}, "serie": []}


def test_registrar_turno_engole_falha_do_banco(monkeypatch):
    """Observar nunca pode atrapalhar atender: se o INSERT falhar, o turno segue."""
    def explode():
        raise RuntimeError("banco fora do ar")
    monkeypatch.setattr(mon, "_conn", explode)
    mon.registrar_turno(lead_id="l1", canal="web", resultado="ok", duracao_ms=10)   # não levanta
    mon.bater("agent")
    mon.amostrar({"inbound": 3})
    assert mon.servicos_parados() == []            # sem banco, ninguém é declarado morto


def test_amostra_guarda_filas_e_conexoes():
    mon.amostrar({"inbound": 3, "outbound-web": 0})
    a = mon.ultima_amostra()
    assert a is not None and a["filas"] == {"inbound": 3, "outbound-web": 0}
    assert a["conexoes_db"] >= 1


def test_servico_calado_aparece_como_parado():
    mon.bater("agent", {"versao": "1"})
    assert mon.servicos_parados() == [], "acabou de bater: está vivo"
    assert [s["servico"] for s in mon.batimentos() if s["vivo"]] == ["agent"]

    with get_pool().connection() as c:            # envelhece o carimbo além do limite
        c.execute("UPDATE batimentos SET em = now() - make_interval(secs => %s)", (mon.PARADO_S + 30,))
    parados = mon.servicos_parados()
    assert [s["servico"] for s in parados] == ["agent"]
    assert parados[0]["ha_segundos"] > mon.PARADO_S
    assert mon.batimentos()[0]["vivo"] is False


def test_bater_duas_vezes_atualiza_em_vez_de_duplicar():
    mon.bater("scheduler")
    mon.bater("scheduler")
    assert len(mon.batimentos()) == 1, "batimentos é um carimbo por serviço, não um histórico"
