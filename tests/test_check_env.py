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


def test_embeddings_fora_do_ollama_e_recusado():
    """Sobrou um provedor de embeddings só, e o schema depende disso: a tabela guarda vetor de 1024
    dimensões (bge-m3). Aceitar outro nome aqui adiaria a falha para a hora de gravar o vetor, que
    é tarde — a ingestão já teria rodado."""
    assert any("SDR_EMBEDDINGS_PROVIDER" in x for x in erros(SDR_EMBEDDINGS_PROVIDER="bedrock"))
    assert any("SDR_EMBEDDINGS_PROVIDER" in x for x in erros(SDR_EMBEDDINGS_PROVIDER="openai"))


def test_provedor_inexistente():
    # `openrouter` existe e funciona — mas é bancada de avaliação, não caminho de produção
    # (ADR-0009). O check_env recusa de propósito, e é justamente isso que este teste protege:
    # um provedor plausível é bem mais fácil de aparecer num .env do que um nome inventado.
    assert any("inválido" in x for x in erros(SDR_LLM_PROVIDER="openrouter"))


def test_openai_e_provedor_valido_mas_exige_a_chave():
    e = erros(SDR_LLM_PROVIDER="openai")
    assert not any("inválido" in x for x in e)
    assert any("OPENAI_API_KEY" in x for x in e)


def test_openai_como_reserva_tambem_exige_a_chave():
    # A reserva só entra em cena quando o primário cai — ou seja, no pior momento possível para
    # descobrir que a credencial nunca foi preenchida.
    assert any("OPENAI_API_KEY" in x for x in erros(SDR_LLM_PROVIDER_FALLBACK="openai"))


def test_reserva_configurada_passa():
    assert erros(SDR_LLM_PROVIDER_FALLBACK="openai", OPENAI_API_KEY="sk-" + "b" * 40) == []


def test_modelo_de_embedding_com_dimensao_diferente_avisa():
    _, avisos = checar({**BASE, "SDR_OLLAMA_EMBEDDING_MODEL": "nomic-embed-text"})
    assert any("1024 dimensões" in a for a in avisos)


def test_variavel_repetida_e_erro(tmp_path):
    """Vale a ÚLTIMA linha — no compose e aqui. Quem descomenta um bloco de exemplo inteiro leva
    junto um `SDR_LLM_PROVIDER=` que não pretendia, e o sistema troca de modelo em silêncio,
    com a linha antiga ainda no arquivo dizendo o contrário. Aconteceu duas vezes neste projeto."""
    from check_env import carregar, checar

    arq = tmp_path / ".env"
    arq.write_text("SDR_LLM_PROVIDER=anthropic\nANTHROPIC_API_KEY=" + CHAVE +
                   "\nSDR_EMBEDDINGS_PROVIDER=ollama\nSDR_LLM_PROVIDER=openai\n", encoding="utf-8")
    env, repetidas = carregar(arq)
    assert repetidas == ["SDR_LLM_PROVIDER"]
    assert env["SDR_LLM_PROVIDER"] == "openai", "a última vence — é o que o compose faz"
    erros = checar(env, repetidas)[0]
    assert any("mais de uma vez" in e for e in erros)


def test_sem_repeticao_nao_inventa_erro(tmp_path):
    from check_env import carregar, checar

    arq = tmp_path / ".env"
    arq.write_text("SDR_LLM_PROVIDER=anthropic\nANTHROPIC_API_KEY=" + CHAVE +
                   "\nSDR_EMBEDDINGS_PROVIDER=ollama\n", encoding="utf-8")
    env, repetidas = carregar(arq)
    assert repetidas == []
    assert checar(env, repetidas)[0] == []
