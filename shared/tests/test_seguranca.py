"""Credencial do painel e `state` do OAuth — os dois portões fora do authorizer do API Gateway."""
import os

import pytest

os.environ["SDR_PROFILE"] = "local"
os.environ["SDR_SESSAO_SECRET"] = "segredo-de-teste"

from sdr_shared.config import get_settings          # noqa: E402
from sdr_shared.seguranca import oauth, painel      # noqa: E402


def _com_ambiente(**env):
    for k, v in env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    get_settings.cache_clear()


def test_painel_local_aceita_token_de_dev():
    _com_ambiente(SDR_PROFILE="local", SDR_PAINEL_TOKEN=None)
    assert painel.valido("dev-token")
    assert not painel.valido("outro") and not painel.valido("") and not painel.valido(None)


def test_painel_fora_do_local_e_fail_closed():
    """Sem SDR_PAINEL_TOKEN configurado, fora do perfil local nada é aceito — nem o token de dev."""
    _com_ambiente(SDR_PROFILE="producao", SDR_PAINEL_TOKEN=None)
    assert not painel.valido("dev-token")
    _com_ambiente(SDR_PAINEL_TOKEN="token-de-producao")
    assert painel.valido("token-de-producao") and not painel.valido("dev-token")
    _com_ambiente(SDR_PROFILE="local", SDR_PAINEL_TOKEN=None)


def test_oauth_state_precisa_ser_emitido_por_nos():
    """O id do corretor é derivado do nome (cor_ana-souza): se o `state` fosse ele cru, bastava
    adivinhar para ligar a própria conta Google à agenda de outra pessoa."""
    assert oauth.validar("cor_ana-souza") is None
    assert oauth.validar("cor_ana-souza.9999999999.assinatura-falsa") is None
    assert oauth.validar(None) is None and oauth.validar("") is None


def test_oauth_state_legitimo_volta_com_o_corretor():
    state = oauth.assinar("cor_ana-souza")
    assert oauth.validar(state) == "cor_ana-souza"
    _corpo, expira, assinatura = state.split(".")
    assert oauth.validar(f"cor_outro.{expira}.{assinatura}") is None, "assinatura é presa ao corretor"


def test_oauth_state_expira():
    assert oauth.validar("cor_ana-souza.1.qualquer") is None


# ---------------------------------------------------------------- cofre

def test_refresh_token_fica_cifrado_no_banco_e_volta_legivel(monkeypatch):
    """Estava em texto puro: um dump do banco carregava a agenda de todos os corretores."""
    import uuid
    from sdr_shared.config import get_settings
    from sdr_shared.db import CorretorRepository
    from sdr_shared.db.connection import get_pool
    from sdr_shared.seguranca import cofre
    monkeypatch.setattr(get_settings(), "sessao_secret", "segredo-de-teste")
    from sdr_shared.models import Corretor
    repo = CorretorRepository()
    cid = f"cofre-{uuid.uuid4().hex[:8]}"
    repo.upsert(Corretor(id=cid, nome="Corretora do Cofre"))
    repo.salvar_credencial_calendario(cid, "1//refresh-super-secreto")
    with get_pool().connection() as conn:
        cru = conn.execute("SELECT calendario_refresh_token FROM corretores WHERE id = %s", (cid,)).fetchone()["calendario_refresh_token"]
    assert cru.startswith(cofre.PREFIXO) and "refresh-super-secreto" not in cru
    assert repo.credencial_calendario(cid) == "1//refresh-super-secreto"
    # valor legado (gravado antes da cifra) continua legível
    with get_pool().connection() as conn:
        conn.execute("UPDATE corretores SET calendario_refresh_token = 'legado-em-claro' WHERE id = %s", (cid,))
    assert repo.credencial_calendario(cid) == "legado-em-claro"
    repo.salvar_credencial_calendario(cid, None)
    assert repo.credencial_calendario(cid) is None


def test_segredo_trocado_nao_vira_token_vazio_em_silencio(monkeypatch):
    from sdr_shared.config import get_settings
    from sdr_shared.seguranca import cofre
    monkeypatch.setattr(get_settings(), "sessao_secret", "chave-a")
    cifrado = cofre.cifrar("x")
    monkeypatch.setattr(get_settings(), "sessao_secret", "chave-b")
    from cryptography.fernet import InvalidToken
    with pytest.raises(InvalidToken):
        cofre.decifrar(cifrado)


def test_sem_segredo_guarda_em_claro_e_avisa(monkeypatch, caplog):
    """Sem SDR_SESSAO_SECRET cada processo teria chave própria: a API cifraria o que o worker
    não lê. Guardar em claro é o comportamento antigo — e o aviso é o que impede o silêncio."""
    from sdr_shared.config import get_settings
    from sdr_shared.seguranca import cofre
    monkeypatch.setattr(get_settings(), "sessao_secret", None)
    monkeypatch.setattr(cofre, "_AVISOU", False)
    with caplog.at_level("WARNING", logger="seguranca"):
        assert cofre.cifrar("x") == "x"
    assert any("sem cifra" in r.message for r in caplog.records)


def test_cors_sem_configuracao_so_libera_os_front_ends_locais(monkeypatch):
    """O vazio era `*`: qualquer site aberto no navegador chamava localhost:8000 com o dev-token."""
    from sdr_shared.config import get_settings
    from sdr_shared.seguranca import cors
    monkeypatch.delenv("SDR_CORS_ORIGINS", raising=False)
    for perfil, esperado in (("local", True), ("producao", False)):
        monkeypatch.setenv("SDR_PROFILE", perfil)
        get_settings.cache_clear()
        o = cors.origens()
        assert "*" not in o
        assert ("http://localhost:5173" in o) is esperado
    monkeypatch.setenv("SDR_CORS_ORIGINS", "https://site.exemplo.com, https://painel.exemplo.com")
    get_settings.cache_clear()
    assert cors.origens() == ["https://site.exemplo.com", "https://painel.exemplo.com"]
    get_settings.cache_clear()


# ---------------------------------------------------------------- S2: chave por finalidade

def test_state_do_oauth_nao_vale_como_token_de_chat_e_vice_versa():
    """Mesmo formato (`<id>.<expira>.<assinatura>`) e, antes, a mesma chave HMAC: o `state` emitido
    para `cor_ana-souza` abria a conversa da sessão `cor_ana-souza`, e o token de chat passava como
    `state` do OAuth. Agora cada finalidade tem a sua chave derivada."""
    from sdr_shared.seguranca import sessao
    state = oauth.assinar("sessao-alvo")
    assert not sessao.validar("sessao-alvo", state)
    s = sessao.emitir()
    assert oauth.validar(s["token"]) is None


def _cifrar_v1(segredo: str, texto: str) -> str:
    """O formato que já está gravado no banco: Fernet com SHA-256("cofre:" + segredo)."""
    import base64
    import hashlib
    from cryptography.fernet import Fernet
    chave = base64.urlsafe_b64encode(hashlib.sha256(f"cofre:{segredo}".encode()).digest())
    return "enc:v1:" + Fernet(chave).encrypt(texto.encode()).decode()


def test_cofre_grava_v2_e_ainda_le_v1_sem_reconectar_a_agenda(monkeypatch):
    import uuid
    from sdr_shared.db import CorretorRepository
    from sdr_shared.db.connection import get_pool
    from sdr_shared.models import Corretor
    from sdr_shared.seguranca import cofre
    monkeypatch.setattr(get_settings(), "sessao_secret", "segredo-de-teste")
    assert cofre.cifrar("x").startswith("enc:v2:")
    assert cofre.decifrar(_cifrar_v1("segredo-de-teste", "1//antigo")) == "1//antigo"

    repo = CorretorRepository()
    cid = f"cofre-{uuid.uuid4().hex[:8]}"
    repo.upsert(Corretor(id=cid, nome="Corretora do v1"))
    with get_pool().connection() as conn:
        conn.execute("UPDATE corretores SET calendario_refresh_token = %s WHERE id = %s",
                     (_cifrar_v1("segredo-de-teste", "1//antigo"), cid))
    assert repo.credencial_calendario(cid) == "1//antigo"
    with get_pool().connection() as conn:
        cru = conn.execute("SELECT calendario_refresh_token FROM corretores WHERE id = %s",
                           (cid,)).fetchone()["calendario_refresh_token"]
    assert cru.startswith("enc:v2:"), "a primeira leitura regrava no formato novo"
    assert repo.credencial_calendario(cid) == "1//antigo"
    repo.salvar_credencial_calendario(cid, None)


def test_v1_cifrado_com_o_segredo_de_exemplo_continua_legivel_depois_de_trocar(monkeypatch):
    """Quem rodou com o valor do .env.example e gerou um segredo de verdade não perde a agenda: o
    v1 com a chave pública é lido (não expõe nada que já não estivesse exposto) e regravado."""
    from sdr_shared.seguranca import cofre
    antigo = _cifrar_v1("dev-local-troque-antes-de-expor-publicamente", "1//do-exemplo")
    monkeypatch.setattr(get_settings(), "sessao_secret", "segredo-novo-de-verdade")
    assert cofre.decifrar(antigo) == "1//do-exemplo"


def test_segredo_de_exemplo_nao_assina_nem_cifra(monkeypatch):
    from sdr_shared.seguranca import cofre, sessao
    from sdr_shared.seguranca.chaves import SegredoDeExemplo
    monkeypatch.setattr(get_settings(), "sessao_secret", "dev-local-troque-antes-de-expor-publicamente")
    with pytest.raises(SegredoDeExemplo, match="token_urlsafe"):
        sessao.emitir()
    with pytest.raises(SegredoDeExemplo):
        oauth.assinar("cor_x")
    with pytest.raises(SegredoDeExemplo):
        cofre.cifrar("x")


def test_servico_recusa_subir_com_o_segredo_de_exemplo(monkeypatch):
    from sdr_shared.seguranca import subida
    monkeypatch.setattr(get_settings(), "sessao_secret", "troque-por-uma-string-aleatoria-longa")
    with pytest.raises(SystemExit, match="token_urlsafe"):
        subida.verificar("api")
    monkeypatch.setattr(get_settings(), "sessao_secret", "um-segredo-gerado-de-verdade")
    subida.verificar("api")


def test_segredo_vazio_usa_chave_do_processo_e_avisa(monkeypatch, caplog):
    from sdr_shared.seguranca import sessao
    monkeypatch.setattr(get_settings(), "sessao_secret", None)
    monkeypatch.setattr(sessao, "_EFEMERO", None)
    with caplog.at_level("WARNING", logger="seguranca"):
        s = sessao.emitir()
    assert sessao.validar(s["session_id"], s["token"])
    assert any("chave aleatória" in r.message for r in caplog.records)


# ---------------------------------------------------------------- S1: dev-token avisa na subida

def test_dev_token_valendo_avisa_na_subida_da_api_e_do_canal(monkeypatch, caplog):
    from sdr_shared.seguranca import subida
    _com_ambiente(SDR_PROFILE="local", SDR_PAINEL_TOKEN=None)
    for servico in ("api", "channels"):
        caplog.clear()
        with caplog.at_level("WARNING", logger="seguranca"):
            subida.verificar(servico)
        assert any("dev-token" in r.message for r in caplog.records), servico
    caplog.clear()
    _com_ambiente(SDR_PAINEL_TOKEN="token-de-verdade")
    with caplog.at_level("WARNING", logger="seguranca"):
        subida.verificar("api")
    assert not any("dev-token" in r.message for r in caplog.records)
    _com_ambiente(SDR_PAINEL_TOKEN=None)
