"""Fila do que não conseguiu ser publicado no CRM, e a drenagem dela.

A porta (`ports/crm.py`) promete desde o início que "a transcrição continua na Mora para ser
publicada depois". Até setembro/2026 essa frase não tinha código atrás: o turno publicado com o CRM
fora do ar virava um `log.warning` e nunca mais era tentado. O corretor abria a ficha e faltava a
conversa exatamente do período em que o CRM esteve instável — que é quando ele mais precisa dela.

O que fica na fila é o TURNO (entrada, texto de saída, ids das mensagens, estágio anterior), não o
lead: o lead é relido do banco na hora de drenar, porque o CRM quer o estado atual, e tudo o que o
publicador faz é idempotente (`external_event_id`, `operation_id`, transição já feita é recusada e
ignorada). Republicar um turno velho com o lead novo é seguro.

Quem drena é o scheduler, no mesmo laço de 30 s do follow-up. Backoff exponencial até uma hora;
depois de `MAX_TENTATIVAS` a linha fica, com o erro, para alguém olhar — apagar em silêncio seria
repetir o defeito que esta fila corrige.
"""
import json
import logging

from ..db.connection import get_pool
from ..messaging import MensagemNormalizada
from ..models import Estagio

log = logging.getLogger("crm")

MAX_TENTATIVAS = 30          # ~1 dia com o backoff abaixo; depois disso a linha fica para inspeção
BACKOFF_MAX_S = 3600


def _chave(lead_id: str, entrada: MensagemNormalizada, id_entrada: int | None) -> str:
    if id_entrada is not None:
        return f"{lead_id}:msg:{id_entrada}"
    return f"{lead_id}:{entrada.recebida_em.isoformat()}"


def registrar(lead_id: str, entrada: MensagemNormalizada, *, texto_saida: str | None,
              estagio_antes: Estagio | None, id_entrada: int | None, id_saida: int | None,
              erro: str) -> None:
    """Guarda o turno para republicar. Nunca levanta: é chamada de dentro de um `except`."""
    turno = {"entrada": entrada.model_dump(mode="json"), "texto_saida": texto_saida,
             "estagio_antes": estagio_antes.value if estagio_antes else None,
             "id_entrada": id_entrada, "id_saida": id_saida}
    try:
        with get_pool().connection() as conn:
            conn.execute(
                """INSERT INTO crm_pendencias (lead_id, chave, turno, ultimo_erro)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (chave) DO UPDATE SET ultimo_erro = EXCLUDED.ultimo_erro""",
                (lead_id, _chave(lead_id, entrada, id_entrada), json.dumps(turno), erro[:500]))
        log.info("turno do lead %s guardado para publicar no CRM depois", lead_id)
    except Exception:
        log.warning("não consegui guardar a pendência do CRM do lead %s", lead_id, exc_info=True)


def pendentes() -> int:
    with get_pool().connection() as conn:
        return conn.execute("SELECT count(*) AS n FROM crm_pendencias").fetchone()["n"]


def drenar(limite: int = 20) -> dict:
    """Republica o que venceu. Devolve contagens para o log do scheduler.

    Uma sessão MCP para o lote inteiro, não uma por turno: o handshake é o custo fixo. Com o CRM
    ainda fora, `sessao()` entrega uma sessão inerte e cada linha volta como "incompleta" — que é
    adiada com backoff. A exceção só aparece em falha inesperada, e aí o resto do lote é adiado.
    """
    from ..db import LeadRepository
    from ..ports import get_crm
    from . import publicador

    saida = {"publicadas": 0, "adiadas": 0, "desistidas": 0}
    crm = get_crm()
    if not crm.habilitado():
        return saida
    with get_pool().connection() as conn:
        linhas = conn.execute(
            """SELECT id, lead_id, turno, tentativas FROM crm_pendencias
                WHERE proxima_em <= now() AND tentativas < %s
                ORDER BY criado_em LIMIT %s""", (MAX_TENTATIVAS, limite)).fetchall()
    if not linhas:
        return saida

    try:
        with crm.sessao() as s:
            for linha in linhas:
                try:
                    lead = LeadRepository().get(linha["lead_id"])
                    if lead is None:
                        _concluir(linha["id"]); continue          # lead apagado: não há o que publicar
                    t = linha["turno"]
                    entrada = MensagemNormalizada.model_validate(t["entrada"])
                    antes = Estagio(t["estagio_antes"]) if t.get("estagio_antes") else None
                    if publicador._publicar(s, lead, entrada, t.get("texto_saida"), antes,
                                            t.get("id_entrada"), t.get("id_saida")):
                        _concluir(linha["id"]); saida["publicadas"] += 1
                    else:
                        _adiar(linha, "publicação incompleta", saida)
                except Exception as e:
                    _adiar(linha, f"{type(e).__name__}: {e}", saida)
    except Exception as e:
        # A sessão não abriu: o CRM continua fora. Adia o que ainda não foi tentado, de uma vez.
        tentadas = saida["publicadas"] + saida["adiadas"] + saida["desistidas"]
        for linha in linhas[tentadas:]:
            _adiar(linha, f"sessão: {type(e).__name__}: {e}", saida)
    return saida


def _concluir(id_: int) -> None:
    with get_pool().connection() as conn:
        conn.execute("DELETE FROM crm_pendencias WHERE id = %s", (id_,))


def _adiar(linha, erro: str, saida: dict) -> None:
    tentativas = linha["tentativas"] + 1
    saida["desistidas" if tentativas >= MAX_TENTATIVAS else "adiadas"] += 1
    espera = min(BACKOFF_MAX_S, 30 * 2 ** min(tentativas, 12))
    with get_pool().connection() as conn:
        conn.execute(
            """UPDATE crm_pendencias SET tentativas = %s, ultimo_erro = %s,
                      proxima_em = now() + make_interval(secs => %s) WHERE id = %s""",
            (tentativas, erro[:500], espera, linha["id"]))
    if tentativas >= MAX_TENTATIVAS:
        log.error("desisti de publicar o turno %s do lead %s no CRM após %d tentativas: %s",
                  linha["id"], linha["lead_id"], tentativas, erro)
