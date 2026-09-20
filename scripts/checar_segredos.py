"""Confere se algum segredo vai junto no push. Rode ANTES de `git push`.

Duas perguntas diferentes, e as duas importam:

1. **Os seus segredos de verdade estão no histórico?** Lê os valores do `local/.env` e procura cada
   um deles em todos os commits. É a checagem de maior valor, porque não depende de o segredo ter
   um formato reconhecível — encontra a chave que alguém colou dentro de um teste, de um exemplo de
   documentação ou de um comentário.

2. **Há algo COM CARA de segredo?** Varredura por padrão (chave da OpenAI, da Anthropic, token de
   bot do Telegram, chave da AWS, token do GitHub, chave privada). Pega o que veio de outra máquina
   ou de outra pessoa, que o seu `.env` não conhece.

Nada de valor de segredo é impresso: só o nome da variável, o arquivo e a linha. Sai com status 1
se achar algo, para poder entrar num hook de pre-push depois.

Uso:
    python3 scripts/checar_segredos.py
    python3 scripts/checar_segredos.py --env local/.env --desde origin/master
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

# Nomes de arquivo que nunca deviam estar versionados.
ARQUIVOS_SUSPEITOS = re.compile(
    r"(^|/)\.env($|\.)|\.pem$|\.p12$|\.pfx$|\.key$|id_rsa|id_ed25519|credentials(\.json)?$", re.I)

# Formatos públicos e estáveis o bastante para valer uma regra. Deixei de fora `sk-[A-Za-z0-9]{20,}`
# genérico: casa com hash de lock file e enche a saída de falso positivo, que é o jeito mais rápido
# de fazer alguém parar de ler o relatório.
PADROES = {
    "chave da Anthropic": r"sk-ant-api[0-9]{2}-[A-Za-z0-9_\-]{80,}",
    "chave da OpenAI": r"sk-(proj-)?[A-Za-z0-9_\-]{40,}",
    "token de bot do Telegram": r"\b[0-9]{8,10}:[A-Za-z0-9_-]{33,}\b",
    "chave da AWS": r"\bAKIA[0-9A-Z]{16}\b",
    "token do GitHub": r"\bgh[pousr]_[A-Za-z0-9]{30,}\b",
    "token do Slack": r"\bxox[baprs]-[A-Za-z0-9-]{10,}",
    "chave privada": r"BEGIN [A-Z ]*PRIVATE KEY",
}

# Arquivos gerados, onde um "achado" é quase sempre hash de dependência.
IGNORAR = [":!*package-lock.json", ":!*.lock", ":!*uv.lock", ":!docs/assets/openapi.json"]


def git(*args: str, checar: bool = False) -> str:
    r = subprocess.run(["git", "-C", str(RAIZ), *args], capture_output=True, text=True)
    if checar and r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} falhou: {r.stderr.strip()}")
    return r.stdout


def valores_do_env(caminho: Path) -> dict[str, str]:
    if not caminho.exists():
        print(f"  ! {caminho} não existe — pulei a checagem dos valores reais")
        return {}
    env = {}
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        k, v = linha.split("=", 1)
        v = v.strip().strip("'\"")
        if len(v) >= 12:                     # abaixo disso não é segredo, é palavra comum
            env[k.strip()] = v
    return env


def exemplos(caminho: Path) -> set[str]:
    """Valores que já estão no `.env.example` versionado: públicos por definição."""
    ex = caminho.with_suffix(caminho.suffix + ".example") if caminho.suffix else Path(f"{caminho}.example")
    if not ex.exists():
        return set()
    return {l.split("=", 1)[1].strip().strip("'\"")
            for l in ex.read_text(encoding="utf-8").splitlines()
            if "=" in l and not l.strip().startswith("#")}


def checar_valores_reais(env: dict[str, str], publicos: set[str]) -> int:
    print("=== 1. valores reais do .env dentro do histórico")
    achados = 0
    for chave, valor in env.items():
        # -S conta ocorrências por commit: acha mesmo o segredo que entrou e depois saiu.
        saida = git("log", "--all", "--oneline", "-S", valor)
        if not saida.strip():
            continue
        n = len(saida.strip().splitlines())
        if valor in publicos:
            print(f"  ok   {chave}: é o valor de exemplo, já público")
        else:
            print(f"  !!!  {chave}: aparece em {n} commit(s) — NÃO EMPURRE")
            achados += 1
    if not achados:
        print("  nenhum segredo real encontrado")
    return achados


def checar_arquivos_rastreados() -> int:
    print("\n=== 2. arquivos de credencial rastreados")
    suspeitos = [f for f in git("ls-files").splitlines()
                 if ARQUIVOS_SUSPEITOS.search(f) and not f.endswith(".example")]
    for f in suspeitos:
        print(f"  !!!  {f}")
    if not suspeitos:
        print("  nenhum")
    return len(suspeitos)


def checar_padroes(desde: str) -> int:
    print(f"\n=== 3. padrões de segredo nos commits de {desde} até HEAD")
    commits = git("rev-list", f"{desde}..HEAD").split() or ["HEAD"]
    # Um LOCAL, um achado. Os padrões se sobrepõem de propósito — a chave da Anthropic começa com
    # `sk-` e também casa com a regra da OpenAI — e relatar a mesma linha duas vezes infla a
    # contagem e faz o relatório parecer pior do que é. Quem lê precisa confiar no número.
    por_local: dict[str, str] = {}
    for nome, padrao in PADROES.items():
        # `-I` pula binário; guardamos arquivo e linha, NUNCA o conteúdo da linha.
        saida = git("grep", "-I", "-n", "-E", padrao, *commits, "--", ".", *IGNORAR)
        for linha in saida.splitlines():
            if linha.strip():
                por_local.setdefault(":".join(linha.split(":")[:3]), nome)
    for local, nome in sorted(por_local.items()):
        print(f"  !!!  {nome}: {local}")
    if not por_local:
        print("  nenhum")
    return len(por_local)


def checar_temporarios() -> int:
    print("\n=== 4. arquivos temporários versionados por engano")
    lixo = [f for f in git("ls-files").splitlines() if f.endswith((".tmp", ".b64", ".orig", ".rej"))]
    for f in lixo:
        print(f"  !    {f}")
    if not lixo:
        print("  nenhum")
    return len(lixo)


def main() -> int:
    p = argparse.ArgumentParser(description="Confere se algum segredo vai junto no push.")
    p.add_argument("--env", default="local/.env", help="arquivo com os segredos reais")
    p.add_argument("--desde", default="origin/master", help="a partir de onde varrer os commits")
    args = p.parse_args()

    caminho = (RAIZ / args.env) if not Path(args.env).is_absolute() else Path(args.env)
    env = valores_do_env(caminho)
    graves = checar_valores_reais(env, exemplos(caminho)) if env else 0
    graves += checar_arquivos_rastreados()
    graves += checar_padroes(args.desde)
    leves = checar_temporarios()

    print()
    if graves:
        print(f"✗ {graves} achado(s) grave(s). NÃO empurre — me mostre o nome da variável, nunca o valor.")
        return 1
    print("✓ nada de credencial no que vai subir." + (f" ({leves} arquivo(s) temporário(s) — só asseio)" if leves else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
