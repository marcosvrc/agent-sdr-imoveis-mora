"""Valida local/.env ANTES de subir o compose — erro de configuração aqui vira erro obscuro lá dentro.

Uso: python scripts/check_env.py [--gerar-segredo] [caminho/do/.env]   (padrão: local/.env)
Sai com status 1 e explica o que corrigir. Não imprime nenhum segredo.

`--gerar-segredo` (usado por `make local`): se SDR_SESSAO_SECRET estiver vazio ou com o valor de
exemplo, grava um aleatório no próprio arquivo antes de conferir.
"""
import re
import secrets
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
# Marcadores que costumam ser colados por engano no lugar do valor real
# Provedores de LLM aceitos. `openrouter` entrou com o ADR-0016 — com retenção zero obrigatória e
# exigindo um reserva DIRETO, porque o OpenRouter fora do ar derruba tudo que passa por ele.
PROVEDORES = {"anthropic", "openai", "ollama", "openrouter"}
# Provedores de embeddings. Todos entregam as 1024 dimensões do schema. Trocar de MODELO obriga a
# reindexar, porque vetor de modelo diferente não se compara com o que já está gravado; trocar só o
# CAMINHO (text-embedding-3-small pela OpenAI ou pelo OpenRouter) não obriga.
EMBEDDINGS = {"ollama", "openai", "openrouter"}
# Valores de SDR_SESSAO_SECRET que já estiveram nos `.env.example` do repositório — os serviços
# recusam subir com eles (sdr_shared/seguranca/chaves.py; repetido aqui porque este script roda com
# o python do sistema, sem as dependências do projeto).
SEGREDOS_DE_EXEMPLO = {"dev-local-troque-antes-de-expor-publicamente", "troque-por-uma-string-aleatoria-longa"}
GERAR_SEGREDO = 'python3 -c "import secrets; print(secrets.token_urlsafe(48))"'
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

    # Segredo público assina sessões e cifra a agenda com uma chave que qualquer um lê no GitHub.
    segredo = env.get("SDR_SESSAO_SECRET", "")
    if segredo in SEGREDOS_DE_EXEMPLO:
        erros.append("SDR_SESSAO_SECRET está com o valor de exemplo do repositório — os serviços "
                     f"recusam subir assim. Gere um: {GERAR_SEGREDO}")
    elif not segredo:
        avisos.append("SDR_SESSAO_SECRET vazio: cada processo usa uma chave aleatória — a API não "
                      "reconhece a sessão emitida pelo canal (os eventos de navegação do site são "
                      "descartados e a Mora perde os imóveis vistos), as sessões de chat caem a cada "
                      "reinício e a agenda do Google fica guardada sem cifra. "
                      f"Gere um: {GERAR_SEGREDO} (ou rode `make local`, que gera sozinho)")
    # O token público só vale no perfil local, e é por isso que as portas ficam em 127.0.0.1.
    if env.get("SDR_PROFILE", "local") == "local" and not env.get("SDR_PAINEL_TOKEN"):
        avisos.append("SDR_PAINEL_TOKEN vazio no perfil local: o token público `dev-token` abre o "
                      "painel (todas as conversas). Defina um antes de expor este ambiente.")

    llm = env.get("SDR_LLM_PROVIDER", "anthropic")
    emb = env.get("SDR_EMBEDDINGS_PROVIDER", "ollama")
    if llm not in PROVEDORES:
        erros.append(f"SDR_LLM_PROVIDER='{llm}' é inválido — use {', '.join(sorted(PROVEDORES))}.")
    if emb not in EMBEDDINGS:
        erros.append(f"SDR_EMBEDDINGS_PROVIDER='{emb}' é inválido — use {', '.join(sorted(EMBEDDINGS))}.")
    if emb == "openrouter" and not env.get("SDR_OPENROUTER_API_KEY"):
        erros.append("SDR_EMBEDDINGS_PROVIDER=openrouter exige SDR_OPENROUTER_API_KEY.")
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

    if "openrouter" in {llm, reserva}:
        if not env.get("SDR_OPENROUTER_API_KEY"):
            erros.append("Provedor openrouter exige SDR_OPENROUTER_API_KEY.")
        if env.get("SDR_OPENROUTER_ZDR", "true").strip().lower() in ("false", "0", "nao", "não", "no"):
            avisos.append("SDR_OPENROUTER_ZDR desligado: o OpenRouter pode rotear para endpoints que "
                          "guardam o texto do cliente. Só para testes com dataset sintético (ADR-0016).")
    if llm == "openrouter" and reserva in ("", "openrouter"):
        avisos.append("OpenRouter como primário sem um reserva DIRETO (anthropic ou openai): se o "
                      "OpenRouter cair, todo modelo cai junto — o fallback interno dele não cobre isso.")

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


def gerar_segredo_se_preciso(caminho: Path) -> bool:
    """Grava um SDR_SESSAO_SECRET aleatório quando o arquivo não tem um de verdade. Devolve se gravou.

    Vazio "funcionava" com um custo escondido: cada processo inventa a própria chave, e a sessão que
    o canal emite não vale na API — os eventos de navegação do site eram descartados em silêncio.
    O valor de exemplo é público. Nenhum dos dois é o que alguém quer ao rodar `make local`."""
    env, _ = carregar(caminho)
    if env.get("SDR_SESSAO_SECRET", "") not in ("", *SEGREDOS_DE_EXEMPLO):
        return False
    novo = f"SDR_SESSAO_SECRET={secrets.token_urlsafe(48)}"
    linhas = caminho.read_text(encoding="utf-8").splitlines()
    trocou = False
    for i, linha in enumerate(linhas):
        if re.match(r"\s*SDR_SESSAO_SECRET\s*=", linha):
            linhas[i] = novo if not trocou else f"# {linha.strip()}   (duplicada, desativada)"
            trocou = True
    if not trocou:
        linhas.append(novo)
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return True


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--gerar-segredo"]
    caminho = Path(args[0]) if args else RAIZ / "local/.env"
    if not caminho.exists():
        print(f"✗ {caminho} não existe. Rode: cp -n local/.env.example local/.env")
        return 1
    exemplo = RAIZ / "local/.env.example"
    if exemplo.exists() and caminho.read_bytes() == exemplo.read_bytes():
        print(f"✗ {caminho} é byte a byte igual ao .env.example — provavelmente foi sobrescrito por")
        print("  um `cp` sem `-n`. Se os containers ainda estiverem no ar, os valores antigos podem")
        print("  ser lidos deles: cd local && docker compose exec agent printenv | grep -E 'SDR_|_KEY'")
        return 1

    if "--gerar-segredo" in sys.argv[1:] and gerar_segredo_se_preciso(caminho):
        print(f"✓ gerei um SDR_SESSAO_SECRET novo em {caminho} (sessões de chat abertas vão cair uma vez)")
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
