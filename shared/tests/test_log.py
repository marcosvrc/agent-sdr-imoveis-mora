"""Log estruturado (ADR-0011): uma linha JSON por evento, com o contexto do turno em toda linha."""
import json
import logging
import os

from sdr_shared import log as slog


def _emitir(record_kwargs=None, **info):
    fmt = slog.FormatadorJSON("agent")
    r = logging.LogRecord("agent", logging.INFO, "f.py", 1, "resposta enviada", (), None)
    for k, v in (record_kwargs or {}).items():
        setattr(r, k, v)
    return json.loads(fmt.format(r))


def setup_function(_):
    slog.limpar_contexto()


def test_linha_tem_servico_origem_e_mensagem():
    d = _emitir()
    assert d["servico"] == "agent" and d["origem"] == "agent" and d["msg"] == "resposta enviada"
    assert d["nivel"] == "INFO" and "em" in d


def test_contexto_entra_em_toda_linha_e_some_ao_limpar():
    slog.contexto(lead_id="l1", canal="telegram", nada=None)
    d = _emitir()
    assert d["lead_id"] == "l1" and d["canal"] == "telegram"
    assert "nada" not in d, "campo None não polui a linha"
    slog.limpar_contexto()
    assert "lead_id" not in _emitir()


def test_campos_do_extra_sobem_para_o_topo():
    """`extra={"campos": {...}}` precisa virar coluna consultável, não um dicionário aninhado."""
    d = _emitir({"campos": {"duracao_ms": 812, "nos": ["supervisor", "consultor"]}})
    assert d["duracao_ms"] == 812 and d["nos"] == ["supervisor", "consultor"]
    assert "campos" not in d


def test_excecao_vira_campo_erro_e_nao_quebra_a_linha():
    fmt = slog.FormatadorJSON("agent")
    try:
        raise ValueError("modelo fora do ar")
    except ValueError:
        import sys
        r = logging.LogRecord("agent", logging.ERROR, "f.py", 1, "falhou", (), sys.exc_info())
    d = json.loads(fmt.format(r))
    assert "ValueError" in d["erro"] and d["nivel"] == "ERROR"


def test_json_desligado_no_perfil_local_e_ligado_fora(monkeypatch):
    """Local é para o olho humano; em produção ninguém lê log com o olho."""
    monkeypatch.delenv("SDR_LOG_JSON", raising=False)
    monkeypatch.setenv("SDR_PROFILE", "local")
    assert slog.json_ligado() is False
    monkeypatch.setenv("SDR_PROFILE", "producao")
    assert slog.json_ligado() is True
    monkeypatch.setenv("SDR_LOG_JSON", "1")         # a variável tem a última palavra
    monkeypatch.setenv("SDR_PROFILE", "local")
    assert slog.json_ligado() is True


def test_configurar_e_idempotente(monkeypatch):
    monkeypatch.setenv("SDR_LOG_JSON", "1")
    slog.configurar("agent")
    slog.configurar("agent")
    assert len(logging.getLogger().handlers) == 1, "chamar duas vezes não pode duplicar a saída"
    os.environ.pop("SDR_LOG_JSON", None)
