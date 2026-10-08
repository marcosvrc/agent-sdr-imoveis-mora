"""Regressões da varredura de segredos (scripts/checar_segredos.py).

O caso que motivou: toda variável do .env com 12+ caracteres era tratada como segredo, e
`SDR_MODEL_CONVERSA=claude-sonnet-4-5` saía como achado GRAVE. Os testes de histórico montam um
repositório git descartável e apontam o script para ele — nunca para o repositório de verdade.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import checar_segredos as cs  # noqa: E402

CHAVE = "sk-ant-api03-" + "a" * 90
TOKEN_TELEGRAM = "123456789:" + "A" * 35


# ---------------------------------------------------------------- o que conta como segredo

@pytest.mark.parametrize("nome,valor", [
    ("SDR_MODEL_CONVERSA", "claude-sonnet-4-5"),
    ("SDR_MODEL_ROTEAMENTO", "anthropic/claude-haiku-4.5"),
    ("SDR_OLLAMA_EMBEDDING_MODEL", "bge-m3-qualquer-coisa"),
    ("SDR_PUBLIC_API_URL", "http://localhost:8000"),
    ("SDR_GOOGLE_REDIRECT_URI", "http://localhost:8000/calendario/callback"),
    ("SDR_TELEGRAM_BOT_USERNAME", "mora_vertice_bot"),
    ("SDR_DATABASE_DSN", "postgresql://sdr:sdr@localhost:5433/sdr"),   # senha do compose, pública
])
def test_valor_publico_nao_e_segredo(nome, valor):
    assert not cs.eh_segredo(nome, valor)


@pytest.mark.parametrize("nome,valor", [
    ("ANTHROPIC_API_KEY", CHAVE),
    ("SDR_TELEGRAM_BOT_TOKEN", TOKEN_TELEGRAM),
    ("SDR_SESSAO_SECRET", "uma-string-aleatoria-de-verdade-9f8e7d"),
    ("CRM_MCP_TOKEN", "kq3V0b1x9Zr8yW2mN4pL6tH"),
    ("SDR_GOOGLE_CLIENT_SECRET", "GOCSPX-abcdefghijklmnop"),
    ("SDR_DATABASE_DSN", "postgresql://app:S3nh4-Forte-De-Verdade@db.interno:5432/sdr"),
])
def test_segredo_de_verdade_e_reconhecido(nome, valor):
    assert cs.eh_segredo(nome, valor)


@pytest.mark.parametrize("valor", [
    "troque-por-uma-string-aleatoria-longa",
    "dev-local-troque-antes-de-expor-publicamente",
    "COLE_A_CHAVE_NOVA_AQUI_000000",
    "wrkspc_xxxxxxxxxxxxxxxxxxxxxxxx",
])
def test_texto_de_exemplo_nao_e_segredo(valor):
    assert not cs.eh_segredo("SDR_SESSAO_SECRET", valor)


def test_valor_curto_nao_e_segredo():
    assert not cs.eh_segredo("SDR_PAINEL_TOKEN", "abc123")


def test_valores_do_env_filtra_por_nome_e_ignora_comentario(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "# comentário\n"
        "SDR_MODEL_CONVERSA=claude-sonnet-4-5\n"
        f"ANTHROPIC_API_KEY={CHAVE}\n"
        f"SDR_TELEGRAM_BOT_TOKEN='{TOKEN_TELEGRAM}'   # do @BotFather\n"
        "SDR_TRANSCRICAO_PROVIDER=whisper_local_bem_longo   # auto | whisper_local | off\n"
        "VAZIA=\n",
        encoding="utf-8")
    assert cs.valores_do_env(env) == {"ANTHROPIC_API_KEY": CHAVE, "SDR_TELEGRAM_BOT_TOKEN": TOKEN_TELEGRAM}


def test_sem_env_pula_a_parte_local(tmp_path, capsys):
    """É o caminho da CI: não há local/.env, e isso não pode virar erro nem achado."""
    assert cs.valores_do_env(tmp_path / "nao-existe.env") == {}
    assert "pulei" in capsys.readouterr().out


# ---------------------------------------------------------------- contra um repositório descartável

def _git(raiz: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(raiz), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    # A imagem python:3.12-slim não traz git, e `make test-docker` roda esta suíte lá dentro.
    if shutil.which("git") is None:
        pytest.skip("git não está instalado neste ambiente")
    raiz = tmp_path / "repo"
    raiz.mkdir()
    _git(raiz, "init", "-q")
    _git(raiz, "config", "user.email", "teste@exemplo.invalid")
    _git(raiz, "config", "user.name", "teste")
    _git(raiz, "config", "commit.gpgsign", "false")
    monkeypatch.setattr(cs, "RAIZ", raiz)

    def commit(nome: str, conteudo: str) -> None:
        (raiz / nome).parent.mkdir(parents=True, exist_ok=True)
        (raiz / nome).write_text(conteudo, encoding="utf-8")
        _git(raiz, "add", "-A")
        _git(raiz, "commit", "-q", "-m", f"adiciona {nome}")
    return commit


def test_nome_de_modelo_no_historico_nao_e_grave(repo, tmp_path):
    """O falso positivo original: o nome do modelo aparece no código E no .env."""
    repo("config.py", 'MODELO = "claude-sonnet-4-5"\n')
    # O git ACHA o valor no histórico — era isso que virava "NÃO EMPURRE"...
    assert cs.checar_valores_reais({"SDR_MODEL_CONVERSA": "claude-sonnet-4-5"}, publicos=set()) == 1
    # ...e agora ele nem chega à busca, porque o nome da variável não é de segredo.
    env = tmp_path / ".env"
    env.write_text("SDR_MODEL_CONVERSA=claude-sonnet-4-5\n", encoding="utf-8")
    assert cs.checar_valores_reais(cs.valores_do_env(env), publicos=set()) == 0


def test_chave_real_no_historico_e_grave(repo):
    repo("teste.py", f'CHAVE = "{CHAVE}"\n')
    assert cs.checar_valores_reais({"ANTHROPIC_API_KEY": CHAVE}, publicos=set()) == 1


def test_valor_que_esta_no_exemplo_nao_e_grave(repo):
    repo("local/.env.example", "SDR_SESSAO_SECRET=segredo-que-e-publico-por-estar-no-exemplo\n")
    valor = "segredo-que-e-publico-por-estar-no-exemplo"
    assert cs.checar_valores_reais({"SDR_SESSAO_SECRET": valor}, publicos={valor}) == 0


def test_padrao_de_token_na_arvore_e_achado(repo):
    repo("docs/exemplo.md", f"use o token {TOKEN_TELEGRAM} no bot\n")
    assert cs.checar_padroes("HEAD") == 1


def test_arvore_limpa_nao_tem_achado(repo):
    repo("README.md", "nada para ver aqui\n")
    assert cs.checar_padroes("HEAD") == 0
    assert cs.checar_arquivos_rastreados() == 0


def test_env_versionado_e_achado_mas_o_exemplo_nao(repo):
    repo("local/.env.example", "SDR_PROFILE=local\n")
    assert cs.checar_arquivos_rastreados() == 0
    repo("local/.env", "SDR_PROFILE=local\n")
    assert cs.checar_arquivos_rastreados() == 1
