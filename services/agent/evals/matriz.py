"""Matriz de avaliação: os candidatos de cada papel, lado a lado, nas suítes daquele papel.

    python -m evals.matriz                      # tudo o que está em evals/matriz.json, 1 repetição
    python -m evals.matriz --papel extracao -n 3
    python -m evals.matriz --plano              # só mostra o que rodaria e quantas chamadas faria
    python -m evals.matriz --fake               # valida o encanamento com LLM falso, sem gastar token

Cada candidato roda num PROCESSO próprio (`python -m evals`), com o modelo dele no lugar do modelo do
papel (`SDR_MODEL_<PAPEL>`) e sem reserva — um candidato que falha tem de aparecer como falha, não
ser salvo em silêncio pelo provedor de reserva. Processo próprio porque configuração, cache de
modelo e catálogo são por processo: trocar o modelo no meio de um processo mediria o anterior.

A tabela junta qualidade (as métricas de cada suíte), custo e latência (lidos de `uso_llm`, que o
callback de governança grava em toda chamada) e falhas técnicas (casos que levantaram exceção — é
onde aparece um modelo sem endpoint com retenção zero, ou um parâmetro que o endpoint recusa).
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .casos import carregar
from .suites import PAPEL_DA_SUITE

AQUI = Path(__file__).parent
ARQUIVO = AQUI / "matriz.json"
RESULTADOS = AQUI / "resultados"

# Chamadas de modelo por caso, para o plano estimar o tamanho da conta antes de gastar.
CHAMADAS_POR_CASO = {"analise": 2}


def _candidatos(cfg: dict, papeis: list[str] | None) -> list[tuple[str, dict, list[str]]]:
    saida = []
    for papel, bloco in cfg.items():
        if papel.startswith("_") or (papeis and papel not in papeis):
            continue
        for suite in bloco["suites"]:
            if PAPEL_DA_SUITE.get(suite) != papel:
                raise SystemExit(f"matriz.json: a suíte {suite!r} não mede o papel {papel!r} "
                                 f"(mede {PAPEL_DA_SUITE.get(suite)!r})")
        for item in bloco["modelos"]:
            alvo = item if isinstance(item, dict) else {"modelo": item}
            alvo.setdefault("provider", "openrouter" if "/" in alvo["modelo"] else
                            os.environ.get("SDR_LLM_PROVIDER", "anthropic"))
            saida.append((papel, alvo, bloco["suites"]))
    return saida


def _ambiente(papel: str, alvo: dict) -> dict:
    env = dict(os.environ)
    env[f"SDR_MODEL_{papel.upper()}"] = alvo["modelo"]
    env["SDR_LLM_PROVIDER"] = alvo["provider"]
    env["SDR_LLM_PROVIDER_FALLBACK"] = ""        # sem reserva: falha do candidato é dado, não ruído
    return env


# Chave que cada provedor lê do ambiente. A matriz roda em subprocessos que herdam ESTE ambiente —
# no modo docker, o do container, que só lê o local/.env quando é criado.
CHAVES = {"openrouter": "SDR_OPENROUTER_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}


def _falta_credencial(alvos) -> str | None:
    """Sem a chave, todo candidato leva 401 em toda chamada e a matriz sai cheia de números iguais
    — que parecem resultado. Melhor recusar antes de começar e dizer o que fazer."""
    faltando = sorted({CHAVES[a["provider"]] for _, a, _ in alvos
                       if a["provider"] in CHAVES and not os.environ.get(CHAVES[a["provider"]])})
    if not faltando:
        return None
    return (f"{', '.join(faltando)} não está no ambiente deste processo. Se a chave já está no "
            "local/.env e você roda com EVAL_EM=docker, o container foi criado antes dela: "
            "cd local && docker compose up -d --force-recreate agent")


def _rodar(papel: str, alvo: dict, suites: list[str], repeticoes: int, falso: bool = False) -> dict:
    cmd = [sys.executable, "-m", "evals", "-n", str(repeticoes)] + (["--fake"] if falso else [])
    for s in suites:
        cmd += ["--suite", s]
    proc = subprocess.run(cmd, cwd=AQUI.parent, env=_ambiente(papel, alvo),
                          capture_output=True, text=True)
    achado = re.search(r"resultado salvo em (\S+\.json)", proc.stdout)
    if not achado:
        saida = (proc.stderr or proc.stdout).strip().splitlines()
        return {"erro": (saida[-1] if saida else f"saiu com código {proc.returncode}")[:200]}
    return json.loads((AQUI.parent / achado.group(1)).read_text(encoding="utf-8"))


def _metricas(resultado: dict, candidato: str | None = None) -> dict:
    """As colunas da tabela. Uma métrica principal por suíte — a que decide o papel."""
    m: dict = {}
    falhas = 0
    for s in resultado.get("suites", []):
        nome = s["suite"]
        falhas += sum(1 for c in s.get("detalhes", []) if str(c.get("detalhe", "")).startswith("exceção"))
        m[f"{nome}: aprovação"] = f"{s['taxa_aprovacao']}%"
        if nome == "extracao":
            m["extracao: acerto por campo"] = f"{s['acerto_por_campo']}%"
            m["extracao: inventados"] = s["alucinacoes"]
        elif nome == "roteamento":
            m["roteamento: via modelo"] = s["via_llm"]
        elif nome == "adversarial":
            m["adversarial: escape"] = f"{s['taxa_de_escape']}%"
        elif nome == "informacoes":
            m["informacoes: cita fonte"] = f"{s['cita_fonte']}%"
            m["informacoes: inventou"] = s["inventou"]
            m["informacoes: sem base ok"] = f"{s['sem_base_ok']}%"
        elif nome == "analise":
            m["analise: estruturada"] = f"{s['estruturada']}%"
    custo = resultado.get("custo") or {}
    m["custo US$"] = custo.get("custo_usd", "—")
    m["latência média ms"] = custo.get("latencia_media_ms", "—")
    m["chamadas"] = custo.get("chamadas", "—")
    m["chamadas com erro"] = custo.get("chamadas_com_erro", "—")
    m["falhas técnicas"] = falhas
    if candidato:
        # Quem atendeu de verdade. Diferente do candidato = número contaminado (fallback,
        # degradação por orçamento, roteamento do provedor para outro modelo).
        modelos = resultado.get("modelo")          # "falso" no modo --fake, dict com modelo real
        usados = (modelos.get("usado") or []) if isinstance(modelos, dict) else []
        outros = sum(u.get("chamadas", 0) for u in usados
                     if isinstance(u, dict) and u.get("modelo") and u["modelo"] != candidato)
        m["atendidas por outro modelo"] = outros
    if custo.get("erro_exemplo"):
        m["_erro"] = custo["erro_exemplo"]
    return m


def _tabela(papel: str, linhas: list[tuple[str, dict]]) -> str:
    colunas = []
    for _, m in linhas:
        colunas += [c for c in m if c not in colunas and not c.startswith("_")]
    cab = "| modelo | " + " | ".join(colunas) + " |"
    sep = "|---|" + "---|" * len(colunas)
    corpo = ["| " + modelo + " | " + " | ".join(str(m.get(c, "—")) for c in colunas) + " |"
             for modelo, m in linhas]
    erros = [f"- `{modelo}`: {m['_erro']}" for modelo, m in linhas if m.get("_erro")]
    rodape = ("\n\nPrimeiro erro de cada candidato com chamadas falhando:\n" + "\n".join(erros)) if erros else ""
    return f"### {papel}\n\n" + "\n".join([cab, sep, *corpo]) + rodape


def main() -> int:
    p = argparse.ArgumentParser(prog="evals.matriz", description="Candidatos por papel, lado a lado")
    p.add_argument("--arquivo", type=Path, default=ARQUIVO)
    p.add_argument("--papel", action="append", help="só este papel (pode repetir)")
    p.add_argument("--modelo", action="append", help="só este candidato (pode repetir)")
    p.add_argument("-n", "--repeticoes", type=int, default=1)
    p.add_argument("--plano", action="store_true", help="mostra o que rodaria, sem chamar modelo")
    p.add_argument("--fake", action="store_true",
                   help="LLM falso em toda rodada: valida a matriz sem gastar token (números sem valor)")
    args = p.parse_args()

    cfg = json.loads(args.arquivo.read_text(encoding="utf-8"))
    alvos = [a for a in _candidatos(cfg, args.papel) if not args.modelo or a[1]["modelo"] in args.modelo]
    total = 0
    print(f"matriz: {len(alvos)} candidato(s) × {args.repeticoes} repetição(ões)")
    for papel, alvo, suites in alvos:
        chamadas = sum(len(carregar(s)) * CHAMADAS_POR_CASO.get(s, 1) for s in suites) * args.repeticoes
        total += chamadas
        print(f"  {papel:12} {alvo['provider']:10} {alvo['modelo']:40} {', '.join(suites):24} ~{chamadas} chamadas")
    print(f"  total: até ~{total} chamadas de modelo (roteamento só chama o modelo na ambiguidade)")
    if args.plano:
        return 0
    if not args.fake and (falta := _falta_credencial(alvos)):
        print(f"\n✗ {falta}", file=sys.stderr)
        return 2

    por_papel: dict[str, list[tuple[str, dict]]] = {}
    brutos = []
    for papel, alvo, suites in alvos:
        print(f"→ {papel}: {alvo['modelo']}…", flush=True)
        r = _rodar(papel, alvo, suites, args.repeticoes, falso=args.fake)
        m = {"erro": r["erro"]} if "erro" in r else _metricas(r, alvo["modelo"])
        por_papel.setdefault(papel, []).append((alvo["modelo"], m))
        brutos.append({"papel": papel, **alvo, "suites": suites, "metricas": m,
                       "resultado": r if "erro" not in r else None})

    agora = datetime.now(timezone.utc)
    md = [f"# Matriz de avaliação — {agora:%Y-%m-%d %H:%M} UTC",
          "", f"{args.repeticoes} repetição(ões) por caso. Custo e latência de `uso_llm`; "
          "falhas técnicas = casos que levantaram exceção.", ""]
    md += [_tabela(papel, linhas) + "\n" for papel, linhas in por_papel.items()]
    RESULTADOS.mkdir(exist_ok=True)
    base = RESULTADOS / f"matriz-{agora:%Y%m%d-%H%M%S}"
    base.with_suffix(".md").write_text("\n".join(md), encoding="utf-8")
    base.with_suffix(".json").write_text(json.dumps({"em": agora.isoformat(), "repeticoes": args.repeticoes,
                                                     "candidatos": brutos}, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    print("\n" + "\n".join(md))
    print(f"\nmatriz salva em {base.with_suffix('.md').relative_to(AQUI.parent)} (e .json, com os briefings)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
