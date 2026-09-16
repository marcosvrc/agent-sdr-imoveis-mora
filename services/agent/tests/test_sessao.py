"""A sessão do chat do site é emitida e assinada pelo servidor — ninguém entra na conversa de outro."""
import time

from sdr_shared.seguranca import emitir, validar
from sdr_shared.seguranca import sessao as mod


def test_sessao_emitida_pelo_servidor_vale():
    s = emitir()
    assert validar(s["session_id"], s["token"])


def test_id_escolhido_pelo_navegador_nao_vale():
    assert not validar("sess-que-eu-inventei", "qualquer-coisa")
    assert not validar("sess-que-eu-inventei", None)


def test_token_de_uma_sessao_nao_serve_para_outra():
    a, b = emitir(), emitir()
    assert not validar(a["session_id"], b["token"]), "trocar o id mantendo o token é o ataque óbvio"


def test_token_adulterado_e_rejeitado():
    s = emitir()
    sid, expira, assinatura = s["token"].split(".")
    esticado = f"{sid}.{int(expira) + 999999}.{assinatura}"       # tentar estender a validade
    assert not validar(sid, esticado)


def test_sessao_expirada_e_rejeitada(monkeypatch):
    s = emitir()
    daqui_a_um_dia = time.time() + mod.VALIDADE_S + 3600
    monkeypatch.setattr(mod.time, "time", lambda: daqui_a_um_dia)
    assert not validar(s["session_id"], s["token"])
