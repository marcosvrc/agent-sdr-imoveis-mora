"""Agregação e saída. Duas regras de honestidade embutidas aqui:

1. Resposta de modelo é ruidosa. Rodar uma vez e cravar um número engana — por isso cada caso roda
   N vezes e o relatório mostra média E dispersão (quantas execuções discordaram entre si).
2. O resultado vai para JSON versionado, com data e modelo, para comparar antes/depois de mexer em
   prompt. Sem isso não é harness, é script.
"""
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

DIR_RESULTADOS = Path(__file__).parent / "resultados"


def _pct(parte: int, total: int) -> float:
    return round(100 * parte / total, 1) if total else 0.0


def resumir(suite: str, execucoes: list[list]) -> dict:
    """`execucoes` = N listas de Resultado (uma por repetição). Consolida por caso."""
    por_caso = defaultdict(list)
    for rodada in execucoes:
        for r in rodada:
            por_caso[r.caso].append(r)

    casos, instaveis = [], 0
    for caso_id, rs in por_caso.items():
        passes = [r.passou for r in rs]
        estavel = len(set(passes)) == 1
        instaveis += 0 if estavel else 1
        casos.append({
            "caso": caso_id,
            "taxa": _pct(sum(passes), len(passes)),
            "estavel": estavel,
            "detalhe": next((r.detalhe for r in rs if r.detalhe), ""),
            "extras": rs[0].extras,
        })

    total = len(casos)
    aprovados = sum(1 for c in casos if c["taxa"] == 100.0)
    resumo = {"suite": suite, "casos": total, "repeticoes": len(execucoes),
              "aprovados": aprovados, "taxa_aprovacao": _pct(aprovados, total),
              "instaveis": instaveis, "detalhes": sorted(casos, key=lambda c: c["taxa"])}

    todos = [r for rodada in execucoes for r in rodada]
    if suite == "extracao":
        ok = sum(r.extras.get("campos_ok", 0) for r in todos)
        tot = sum(r.extras.get("campos_total", 0) for r in todos)
        resumo["acerto_por_campo"] = _pct(ok, tot)
        resumo["alucinacoes"] = sum(r.extras.get("alucinacoes", 0) for r in todos)
        piores = Counter(c for r in todos for c in r.extras.get("campos_errados", []))
        resumo["campos_mais_errados"] = piores.most_common(5)
    elif suite == "roteamento":
        resumo["via_llm"] = sum(1 for r in todos if r.extras.get("via_llm"))
        confusao = Counter((r.extras.get("esperado"), r.extras.get("obtido"))
                           for r in todos if r.extras.get("esperado") != r.extras.get("obtido"))
        resumo["confusoes"] = [{"esperado": e, "obtido": o, "n": n} for (e, o), n in confusao.most_common()]
    elif suite == "adversarial":
        camadas = Counter(r.extras.get("camada") for r in todos)
        resumo["barrado_pela_regra"] = camadas.get("regra", 0)
        resumo["barrado_pelo_modelo"] = camadas.get("modelo", 0)
        resumo["escapou"] = camadas.get("escapou", 0)
        resumo["taxa_de_escape"] = _pct(camadas.get("escapou", 0), len(todos))
        por_cat = defaultdict(lambda: [0, 0])
        for r in todos:
            por_cat[r.extras.get("categoria") or "?"][0] += 0 if r.passou else 1
            por_cat[r.extras.get("categoria") or "?"][1] += 1
        resumo["escape_por_categoria"] = {k: f"{v[0]}/{v[1]}" for k, v in sorted(por_cat.items())}
    elif suite == "rag":
        positivos = [r for r in todos if not r.extras.get("abstencao")]
        obvias = [r for r in todos if r.extras.get("abstencao") and r.extras.get("tipo") != "adjacente"]
        adjacentes = [r for r in todos if r.extras.get("abstencao") and r.extras.get("tipo") == "adjacente"]

        resumo["recall_em_3"] = _pct(sum(1 for r in positivos if r.passou), len(positivos))
        # Precisão no topo importa por si: o nó manda TRÊS trechos ao modelo, e o primeiro é o que
        # vira a fonte citada ao cliente. Recall alto com topo errado é uma citação errada.
        resumo["acerto_no_topo"] = _pct(sum(1 for r in positivos if r.extras.get("no_topo")), len(positivos))
        resumo["abstencao_obvia"] = _pct(sum(1 for r in obvias if r.passou), len(obvias))
        # Reportada à parte: aqui abster é conservador e responder pode ser extrapolar. A escolha é
        # de produto e não deve ser diluída na média das negativas fáceis.
        resumo["abstencao_adjacente"] = _pct(sum(1 for r in adjacentes if r.passou), len(adjacentes))

        # A distribuição de score é o que permite calibrar o piso com evidência em vez de no olho.
        acertos = sorted(r.extras["score_topo"] for r in positivos
                         if r.passou and r.extras.get("score_topo") is not None)
        enganos = sorted(r.extras["score_topo"] for r in todos
                         if not r.passou and r.extras.get("score_topo") is not None)
        resumo["score_acertos"] = {"min": acertos[0], "mediana": acertos[len(acertos) // 2]} if acertos else None
        resumo["score_enganos_max"] = enganos[-1] if enganos else None
    return resumo


def custo_da_execucao(desde: datetime) -> dict:
    """Custo e latência saem de graça da governança: o callback de uso já grava cada chamada."""
    try:
        from sdr_shared.db import get_pool
        with get_pool().connection() as c:
            r = c.execute("""SELECT count(*) n, coalesce(sum(custo), 0) custo,
                                    coalesce(avg(latencia_ms), 0) lat
                             FROM uso_llm WHERE em >= %s""", (desde,)).fetchone()
        return {"chamadas": int(r["n"]), "custo_usd": round(float(r["custo"]), 4),
                "latencia_media_ms": int(r["lat"])}
    except Exception as e:                       # governança é bônus: não derruba o relatório
        return {"erro": str(e)[:120]}


def imprimir(resumos: list[dict], custo: dict) -> None:
    print()
    for r in resumos:
        print(f"── {r['suite']}  ({r['casos']} casos × {r['repeticoes']} repetição(ões))")
        print(f"   aprovação: {r['taxa_aprovacao']}%  ({r['aprovados']}/{r['casos']})", end="")
        print(f"   instáveis entre execuções: {r['instaveis']}" if r["instaveis"] else "")
        if r["suite"] == "extracao":
            print(f"   acerto por campo: {r['acerto_por_campo']}%   campos inventados: {r['alucinacoes']}")
            if r["campos_mais_errados"]:
                print("   piores campos: " + ", ".join(f"{c}({n})" for c, n in r["campos_mais_errados"]))
        if r["suite"] == "roteamento":
            print(f"   decisões via modelo: {r['via_llm']} (o resto foi regra determinística)")
            for c in r["confusoes"][:5]:
                print(f"   confundiu {c['esperado']} → {c['obtido']} ({c['n']}x)")
        if r["suite"] == "adversarial":
            print(f"   barrado pela regra: {r['barrado_pela_regra']}   "
                  f"barrado pelo modelo: {r['barrado_pelo_modelo']}   escapou: {r['escapou']}")
            print(f"   TAXA DE ESCAPE: {r['taxa_de_escape']}%   por categoria: {r['escape_por_categoria']}")
        if r["suite"] == "rag":
            print(f"   recall@3: {r['recall_em_3']}%   acerto no topo: {r['acerto_no_topo']}%")
            print(f"   abstenção (óbvias): {r['abstencao_obvia']}%   "
                  f"(adjacentes, decisão de produto): {r['abstencao_adjacente']}%")
            acertos, engano = r.get("score_acertos"), r.get("score_enganos_max")
            if acertos and engano is not None:
                print(f"   score: acertos min {acertos['min']} / mediana {acertos['mediana']}   "
                      f"maior score de engano {engano}")
                if engano >= acertos["min"]:
                    # O piso separa por score; quando o pior acerto pontua abaixo do melhor engano,
                    # NENHUM limiar separa os dois. Dizer isso é mais útil que imprimir o número e
                    # deixar quem lê concluir que basta ajustar o piso.
                    print("   ⚠ nenhum piso separa acerto de engano neste conjunto — "
                          "calibrar o limiar não resolve; o que falta é recuperação melhor")
        for c in r["detalhes"]:
            if c["taxa"] < 100.0:
                print(f"   ✗ {c['caso']} ({c['taxa']}%) {c['detalhe'][:110]}")
        print()
    if custo.get("chamadas"):
        print(f"── custo desta execução: US$ {custo['custo_usd']} em {custo['chamadas']} chamadas, "
              f"latência média {custo['latencia_media_ms']}ms")


def salvar(resumos: list[dict], custo: dict, modelo: str) -> Path:
    DIR_RESULTADOS.mkdir(exist_ok=True)
    agora = datetime.now(timezone.utc)
    caminho = DIR_RESULTADOS / f"{agora:%Y%m%d-%H%M%S}.json"
    caminho.write_text(json.dumps(
        {"em": agora.isoformat(), "modelo": modelo, "custo": custo, "suites": resumos},
        ensure_ascii=False, indent=2), encoding="utf-8")
    return caminho
