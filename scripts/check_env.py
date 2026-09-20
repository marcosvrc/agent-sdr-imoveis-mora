"""Valida local/.env ANTES de subir o compose — erro de configuração aqui vira erro obscuro lá dentro.

Uso: python scripts/check_env.py [caminho/do/.env]   (padrão: local/.env)
Sai com status 1 e explica o que corrigir. Não imprime nenhum segredo.
"""
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
# Marcadores que costumam ser colados por engano no lugar do valor real
# Provedores de LLM aceitos. `openrouter` fica de fora de propósito: é bancada de avaliação, não
# caminho de produção (ADR-0009).
PROVEDORES = {"anthropic", "openai", "ollama"}
# Provedores de embeddings. Os dois entregam as 1024 dimensões do schema; trocar entre eles obriga
# a reindexar, porque vetor de modelo diferente não se compara com o que já está gravado.
EMBEDDINGS = {"ollama", "openai"}
PLACEHOLDERS = re.compile(r"(COLE_|SEU_ID|SEU_|CHANGE_?ME|<.*>|xxx+|placeholder|preencher)", re.I)


def carregar(caminho: Path) -> tuple[dict[str, str], list[str]]:
    """Devolve as variáveis e as que aparecem MAIS DE UMA VEZ.

    A duplicata importa e não é cosmética: tanto o `env_file` do compose quanto este arquivo
    resolvem a repetição pela ÚLTIMA linha. Quem descomenta um bloco de exemplo inteiro leva junto
    um `SDR_LLM_PROVIDER=` que não pretendia, e o sistema troca de modelo em silêncio — a primeira
    linha continua lá, legível, dizendo o contrário do que vale. Já aconteceu duas vezes aqui: uma
    com o token do CRM, outra com o provedor de LLM.
    """
    env: dict[str, str] = {}
    vistas: list[str] = []
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        k, v = linha.split("=", 1)
        k = k.strip()
        vistas.append(k)
        env[k] = v.strip().strip("'\"")
    repetidas = sorted({k for k in vistas if vistas.count(k) > 1})
    return env, repetidas


def checar(env: dict[str, str], repetidas: list[str] | None = None) -> tuple[list[str], list[str]]:
    erros, avisos = [], []

    for chave in repetidas or []:
        erros.append(f"{chave} aparece mais de uma vez — vale a ÚLTIMA linha, e a primeira fica no "
                     f"arquivo dizendo o contrário. Apague a que sobra.")

    for k, v in env.items():
        if v and PLACEHOLDERS.search(v):
            erros.append(f"{k} ainda está com um texto de exemplo, não com o valor real.")

    llm = env.get("SDR_LLM_PROVIDER", "anthropic")
    emb = env.get("SDR_EMBEDDINGS_PROVIDER", "ollama")
    if llm not in PROVEDORES:
        erros.append(f"SDR_LLM_PROVIDER='{llm}' é inválido — use {', '.join(sorted(PROVEDORES))}.")
    if emb not in EMBEDDINGS:
        erros.append(f"SDR_EMBEDDINGS_PROVIDER='{emb}' é inválido — use {', '.join(sorted(EMBEDDINGS))}.")
    if emb == "openai" and not env.get("OPENAI_API_KEY"):
        erros.append("SDR_EMBEDDINGS_PROVIDER=openai exige OPENAI_API_KEY (sem o prefixo SDR_ — é o "
                     "nome que a biblioteca procura no ambiente).")
    dim = env.get("SDR_EMBEDDINGS_DIMENSOES", "1024")
    if dim != "1024":
        # Não é preferência: `imoveis.embedding` e `documentos.embedding` são `vector(1024)`, e
        # gravar outro tamanho não degrada — recusa, no meio da indexação.
        erros.append(f"SDR_EMBEDDINGS_DIMENSOES={dim} não casa com o `vector(1024)` do schema. "
                     "Mudar exige alterar shared/sdr_shared/db/schema.sql e reindexar.")

    if llm == "anthropic":
        chave = env.get("ANTHROPIC_API_KEY", "")
        if not chave:
            erros.append("SDR_LLM_PROVIDER=anthropic exige ANTHROPIC_API_KEY.")
        elif not re.fullmatch(r"sk-ant-api\d{2}-[\w\-]{60,}", chave):
            erros.append("ANTHROPIC_API_KEY não tem cara de chave da Anthropic "
                         f"(esperado sk-ant-apiNN-…; recebido {len(chave)} caracteres).")
        ws = env.get("SDR_ANTHROPIC_WORKSPACE_ID", "")
        if ws and not ws.startswith("wrkspc_"):
            erros.append("SDR_ANTHROPIC_WORKSPACE_ID deve começar com 'wrkspc_' "
                         "(copie da URL do workspace no Console) ou ficar vazio.")

    # Reserva: mesmo conjunto de provedores, e só serve para alguma coisa se for OUTRO provedor.
    reserva = env.get("SDR_LLM_PROVIDER_FALLBACK", "").strip()
    if reserva and reserva not in PROVEDORES:
        erros.append(f"SDR_LLM_PROVIDER_FALLBACK='{reserva}' é inválido — use {', '.join(sorted(PROVEDORES))}.")
    if reserva and reserva == llm:
        avisos.append(f"SDR_LLM_PROVIDER_FALLBACK={reserva} é o mesmo do primário: o fallback fica desligado.")
    if not reserva:
        avisos.append("Sem SDR_LLM_PROVIDER_FALLBACK: se o provedor cair, cada turno vira mensagem de "
                      "desculpa e encaminhamento ao corretor.")

    if "openai" in {llm, reserva}:
        chave = env.get("OPENAI_API_KEY", "")
        if not chave:
            erros.append("Provedor openai exige OPENAI_API_KEY (sem o prefixo SDR_ — é o nome que a "
                         "biblioteca procura no ambiente).")
        elif not chave.startswith("sk-"):
            erros.append("OPENAI_API_KEY não tem cara de chave da OpenAI (esperado sk-…).")

    if emb == "ollama":
        modelo = env.get("SDR_OLLAMA_EMBEDDING_MODEL", "bge-m3")
        if modelo != "bge-m3":
            avisos.append(f"SDR_OLLAMA_EMBEDDING_MODEL={modelo}: o schema espera 1024 dimensões "
                          "(bge-m3). Outro modelo exige alterar shared/sdr_shared/db/schema.sql.")
        avisos.append("Embeddings no Ollama: suba com `make local-ollama` e rode `make ollama-pull` uma vez.")

    # CRM: dois segredos distintos, e trocá-los um pelo outro dá 401 sem explicação. O servidor MCP
    # RECUSA subir sem o dele, então a falta aparece como um container que sai — sintoma que não
    # aponta para a causa. Conferir aqui é o que transforma isso numa linha legível.
    mcp_token, api_token = env.get("CRM_MCP_TOKEN", ""), env.get("CRM_API_TOKEN", "")
    if mcp_token and len(mcp_token) < 24:
        erros.append(f"CRM_MCP_TOKEN tem só {len(mcp_token)} caracteres. Gere um forte: "
                     "python3 -c \"import secrets; print(secrets.token_urlsafe(32))\"")
    if mcp_token and not api_token:
        avisos.append("CRM_MCP_TOKEN definido mas CRM_API_TOKEN vazio: o servidor MCP sobe e não "
                      "consegue falar com a API do CRM. Emita com `make crm-token` e cole aqui.")
    if api_token and not mcp_token:
        erros.append("CRM_API_TOKEN definido mas CRM_MCP_TOKEN vazio — o servidor MCP recusa "
                     "iniciar sem ele, e o container vai sair sem explicar por quê.")
    if not mcp_token and not api_token:
        avisos.append("CRM não configurado — a Mora roda normalmente sozinha. Para ligar, veja a "
                      "seção do CRM em local/.env.example.")

    return erros, avisos


def main() -> int:
    caminho = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / "local/.env"
    if not caminho.exists():
        print(f"✗ {caminho} não existe. Rode: cp -n local/.env.example local/.env")
        return 1
    exemplo = RAIZ / "local/.env.example"
    if exemplo.exists() and caminho.read_bytes() == exemplo.read_bytes():
        print(f"✗ {caminho} é byte a byte igual ao .env.example — provavelmente foi sobrescrito por")
        print("  um `cp` sem `-n`. Se os containers ainda estiverem no ar, os valores antigos podem")
        print("  ser lidos deles: cd local && docker compose exec agent printenv | grep -E 'SDR_|_KEY'")
        return 1

    env, repetidas = carregar(caminho)
    erros, avisos = checar(env, repetidas)
    for a in avisos:
        print(f"! {a}")
    for e in erros:
        print(f"✗ {e}")
    if erros:
        print(f"\n{len(erros)} problema(s) em {caminho}. Corrija antes de subir o compose.")
        return 1
    print(f"✓ {caminho} está coerente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
