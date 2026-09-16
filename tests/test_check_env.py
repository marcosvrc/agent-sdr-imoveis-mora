"""Regressões dos erros de configuração que realmente aconteceram ao ligar o perfil local."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_env import checar  # noqa: E402

CHAVE = "sk-ant-api03-" + "a" * 70
BASE = {"SDR_PROFILE": "local", "SDR_LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": CHAVE,
        "SDR_EMBEDDINGS_PROVIDER": "ollama", "SDR_OLLAMA_EMBEDDING_MODEL": "bge-m3"}


def erros(**mudancas):
    return checar({**BASE, **mudancas})[0]


def test_configuracao_valida_nao_tem_erro():
    assert erros() == []


def test_placeholder_colado_no_lugar_da_chave():
    assert any("texto de exemplo" in e for e in erros(ANTHROPIC_API_KEY="COLE_A_CHAVE_NOVA_AQUI"))


def test_placeholder_colado_no_workspace():
    assert any("texto de exemplo" in e for e in erros(SDR_ANTHROPIC_WORKSPACE_ID="wrkspc_SEU_ID"))


def test_workspace_id_com_formato_errado():
    assert any("wrkspc_" in e for e in erros(SDR_ANTHROPIC_WORKSPACE_ID="minha-empresa"))


def test_workspace_id_valido_passa():
    assert erros(SDR_ANTHROPIC_WORKSPACE_ID="wrkspc_01ABCdef") == []


def test_chave_truncada():
    assert any("cara de chave" in e for e in erros(ANTHROPIC_API_KEY="sk-ant-api03-curta"))


def test_anthropic_com_embeddings_bedrock_sem_credencial():
    e = erros(SDR_EMBEDDINGS_PROVIDER="bedrock")
    assert any("não tem API de embeddings" in x for x in e)
    assert any("credenciais AWS" in x for x in e)


def test_bedrock_sem_credenciais():
    e = checar({"SDR_LLM_PROVIDER": "bedrock", "SDR_EMBEDDINGS_PROVIDER": "bedrock"})[0]
    assert any("credenciais AWS" in x for x in e)


def test_bedrock_com_credenciais_passa():
    e = checar({"SDR_LLM_PROVIDER": "bedrock", "SDR_EMBEDDINGS_PROVIDER": "bedrock",
                "AWS_ACCESS_KEY_ID": "AKIA...", "AWS_SECRET_ACCESS_KEY": "segredo"})[0]
    assert e == []


def test_provedor_inexistente():
    assert any("inválido" in x for x in erros(SDR_LLM_PROVIDER="openai"))


def test_modelo_de_embedding_com_dimensao_diferente_avisa():
    _, avisos = checar({**BASE, "SDR_OLLAMA_EMBEDDING_MODEL": "nomic-embed-text"})
    assert any("1024 dimensões" in a for a in avisos)
