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

        resumo["fusao_lexica"] = bool(todos and todos[0].extras.get("lexico"))
        resumo["recall_em_3"] = _pct(sum(1 for r in positivos if r.passou), len(positivos))
        # Paráfrase e literal saem separadas: a primeira pesa a favor do denso, a segunda a favor
        # do léxico, e uma média única esconderia qualquer um dos dois estar quebrado.
        parafrase = [r for r in positivos if r.extras.get("tipo") != "literal"]
        literais = [r for r in positivos if r.extras.get("tipo") == "literal"]
        resumo["recall_parafrase"] = _pct(sum(1 for r in parafrase if r.passou), len(parafrase))
        resumo["recall_literal"] = _pct(sum(1 for r in literais if r.passou), len(literais))
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
    elif suite == "informacoes":
        com_fonte = [r for r in todos if r.extras.get("sem_base") is False]
        sem_base = [r for r in todos if r.extras.get("sem_base")]
        resumo["cita_fonte"] = _pct(sum(1 for r in com_fonte if r.extras.get("cita_fonte")), len(com_fonte))
        # O número que decide o papel: resposta sobre política da empresa com valor que não está
        # no documento é exatamente a informação falsa que este nó existe para impedir.
        resumo["inventou"] = sum(1 for r in todos if r.extras.get("inventou"))
        resumo["sem_base_ok"] = _pct(sum(1 for r in sem_base if r.passou), len(sem_base))
    elif suite == "analise":
        resumo["estruturada"] = _pct(sum(1 for r in todos if r.extras.get("estruturada")), len(todos))
    return resumo


def custo_da_execucao(desde: datetime) -> dict:
    """Custo e latência saem de graça da governança: o callback de uso já grava cada chamada."""
    try:
        from sdr_shared.db import get_pool
        with get_pool().connection() as c:
            # `custo_usd` é o nome da coluna em `uso_llm` (schema.sql). Enquanto aqui dizia
            # `custo`, toda execução gravava `{"erro": "column \"custo\" does not exist"}` no
            # lugar do custo — e como a governança é bônus e o except engole, nenhum eval jamais
            # reportou quanto custou.
            r = c.execute("""SELECT count(*) n, coalesce(sum(custo_usd), 0) custo,
                                    coalesce(avg(latencia_ms) FILTER (WHERE erro IS NULL), 0) lat,
                                    count(*) FILTER (WHERE erro IS NOT NULL) erros,
                                    (array_agg(erro ORDER BY em) FILTER (WHERE erro IS NOT NULL))[1] exemplo
                             FROM uso_llm WHERE em >= %s""", (desde,)).fetchone()
        # Chamada com erro não é chamada rápida: a latência média conta só as que responderam, e o
        # erro aparece à parte. Muitas suítes engolem a exceção (a extração devolve o cartão sem
        # mudança), então sem esta contagem um modelo que falha em tudo parece só um modelo ruim.
        return {"chamadas": int(r["n"]), "custo_usd": round(float(r["custo"]), 4),
                "latencia_media_ms": int(r["lat"]), "chamadas_com_erro": int(r["erros"]),
                "erro_exemplo": (r["exemplo"] or "")[:300] or None}
    except Exception as e:                       # governança é bônus: não derruba o relatório
        return {"erro": str(e)[:120]}


def modelos_configurados() -> dict:
    """O que o agente usaria agora, por papel — painel do banco em uso, senão o ambiente.

    O relatório gravava `os.getenv("SDR_MODEL_CONVERSA", "padrão")`: sem a variável exportada saía
    "padrão", o painel era ignorado e o papel de roteamento nem aparecia. Um resultado que não diz
    com qual modelo foi medido não serve para comparar antes e depois de trocar de modelo. A
    resolução é a MESMA do agente (`modelo_efetivo`), para o relatório não ter opinião própria.
    """
    from sdr_shared.config import get_settings
    from sdr_shared.papeis import PAPEIS
    from sdr_shared.ports.factory import modelo_efetivo
    s = get_settings()
    saida: dict = {p: modelo_efetivo(p) for p in PAPEIS}
    try:
        from sdr_shared.db import reserva_do_painel
        reserva = reserva_do_painel()
    except Exception:
        reserva = None
    reserva = reserva or (s.llm_provider_fallback or "").strip() or None
    saida["reserva"] = None if reserva == "nenhum" else reserva
    emb = (s.embeddings_provider or "").strip().lower()
    saida["embeddings"] = {"provider": emb,
                           "modelo": s.ollama_embedding_model if emb == "ollama" else s.embeddings_model}
    return saida


def modelos_usados(desde: datetime) -> list[dict]:
    """O que de fato atendeu, lido de `uso_llm`. É aqui que um fallback durante o eval aparece —
    o configurado diria Anthropic, e parte dos números teria vindo da OpenAI."""
    try:
        from sdr_shared.db import get_pool
        with get_pool().connection() as c:
            linhas = c.execute("""SELECT papel, provider, modelo, count(*) n
                                  FROM uso_llm WHERE em >= %s
                                  GROUP BY papel, provider, modelo ORDER BY n DESC""",
                               (desde,)).fetchall()
        return [{"papel": r["papel"], "provider": r["provider"], "modelo": r["modelo"],
                 "chamadas": int(r["n"])} for r in linhas]
    except Exception as e:                       # governança é bônus: não derruba o relatório
        return [{"erro": str(e)[:120]}]


def modelos_da_execucao(desde: datetime) -> dict:
    return {"configurado": modelos_configurados(), "usado": modelos_usados(desde)}


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
            print(f"   fusão léxica: {'LIGADA' if r.get('fusao_lexica') else 'desligada'} "
                  f"(SDR_RAG_LEXICO)")
            print(f"   recall@3: {r['recall_em_3']}%   acerto no topo: {r['acerto_no_topo']}%")
            print(f"   por forma da pergunta — paráfrase: {r['recall_parafrase']}%   "
                  f"literal: {r['recall_literal']}%")
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
        if r["suite"] == "informacoes":
            print(f"   cita a fonte: {r['cita_fonte']}%   respostas com número inventado: {r['inventou']}   "
                  f"sem base, diz que confirma: {r['sem_base_ok']}%")
        if r["suite"] == "analise":
            print(f"   análise estruturada válida: {r['estruturada']}%  (os briefings estão no JSON do resultado)")
        for c in r["detalhes"]:
            if c["taxa"] < 100.0:
                print(f"   ✗ {c['caso']} ({c['taxa']}%) {c['detalhe'][:110]}")
        print()
    if custo.get("chamadas"):
        print(f"── custo desta execução: US$ {custo['custo_usd']} em {custo['chamadas']} chamadas, "
              f"latência média {custo['latencia_media_ms']}ms")
    if custo.get("chamadas_com_erro"):
        print(f"── ⚠ {custo['chamadas_com_erro']} chamada(s) com erro — a primeira: {custo['erro_exemplo']}")


def salvar(resumos: list[dict], custo: dict, modelo: str | dict) -> Path:
    DIR_RESULTADOS.mkdir(exist_ok=True)
    agora = datetime.now(timezone.utc)
    caminho = DIR_RESULTADOS / f"{agora:%Y%m%d-%H%M%S}.json"
    caminho.write_text(json.dumps(
        {"em": agora.isoformat(), "modelo": modelo, "custo": custo, "suites": resumos},
        ensure_ascii=False, indent=2), encoding="utf-8")
    return caminho
