"""O indicador de "digitando…" acende já, renova enquanto não há resposta e apaga quando ela sai."""
import httpx

import canal_telegram.digitando as dig


def _bot(monkeypatch):
    acoes = []
    real = httpx.Client
    def tratar(req):
        acoes.append(req.url.path.rsplit("/", 1)[-1])
        return httpx.Response(200, json={"ok": True})
    monkeypatch.setattr(dig.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(tratar)))
    return acoes


def _rodar_ate_o_fim(monkeypatch):
    """Executa o laço na própria thread do teste: sem esperas reais nem corrida."""
    class Imediata:
        def __init__(self, target, args, **kw): self.alvo, self.args = target, args
        def start(self): self.alvo(*self.args)
    monkeypatch.setattr(dig.threading, "Thread", Imediata)


def test_renova_ate_a_resposta_aparecer_e_para(monkeypatch):
    acoes = _bot(monkeypatch)
    _rodar_ate_o_fim(monkeypatch)
    respostas = iter([False, False, True])            # a Mora responde na terceira checagem
    assert dig.iniciar("https://api.telegram.org/botX", "555", "tg_555",
                       respondeu=lambda *_: next(respostas), dormir=lambda _s: None)
    assert acoes == ["sendChatAction", "sendChatAction"]
    assert "555" not in dig._ativos, "terminou e liberou o chat"


def test_teto_desliga_turno_que_nunca_responde(monkeypatch):
    acoes = _bot(monkeypatch)
    _rodar_ate_o_fim(monkeypatch)
    relogio = iter(range(0, 1000, 10))                # cada volta "passa" 10 s
    monkeypatch.setattr(dig.time, "monotonic", lambda: next(relogio))
    dig.iniciar("https://api.telegram.org/botX", "555", "tg_555", respondeu=lambda *_: False, dormir=lambda _s: None)
    assert 1 <= len(acoes) <= int(dig.TETO_S // 10) + 1


def test_mensagens_seguidas_nao_abrem_um_indicador_por_mensagem(monkeypatch):
    _bot(monkeypatch)
    monkeypatch.setitem(dig._ativos, "555", object())
    assert dig.iniciar("https://api.telegram.org/botX", "555", "tg_555", respondeu=lambda *_: True) is False


def test_falha_do_telegram_nao_derruba_nem_vaza_token(monkeypatch, caplog):
    _rodar_ate_o_fim(monkeypatch)
    real = httpx.Client
    def quebra(req): raise httpx.ConnectError("sem rede", request=req)
    monkeypatch.setattr(dig.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(quebra)))
    respostas = iter([False, True])
    caplog.set_level("DEBUG")
    dig.iniciar("https://api.telegram.org/botSEGREDO", "555", "tg_555",
                respondeu=lambda *_: next(respostas), dormir=lambda _s: None)
    assert "SEGREDO" not in caplog.text
