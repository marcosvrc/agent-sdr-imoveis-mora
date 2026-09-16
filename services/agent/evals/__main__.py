"""Runner do harness.

    python -m evals                          # tudo, 1 repetição, modelo real
    python -m evals --suite extracao -n 3    # só extração, 3 repetições
    python -m evals --fake                   # LLM falso: testa o harness sem gastar token

Fora do CI de commit de propósito: chama modelo de verdade, custa dinheiro e varia entre execuções.
O portão de commit continua sendo `make test`, que é determinístico.
"""
import argparse
import os
import sys
import traceback
from datetime import datetime, timezone

os.environ.setdefault("SDR_DATABASE_DSN", "postgresql://sdr:sdr@localhost:5433/sdr_test")
os.environ.setdefault("SDR_PROFILE", "local")

from sdr_shared.db.guarda_teste import exigir_banco_de_teste  # noqa: E402

from . import relatorio  # noqa: E402
from .casos import carregar  # noqa: E402
from .suites import SUITES, _trechos_do_prompt  # noqa: E402


def _usar_llm_falso() -> None:
    """Mesmo fake da suíte de testes: serve para validar o harness (datasets, métricas, relatório)
    sem chamar a API. Os números que ele produz não significam nada sobre o modelo — só provam que
    o encanamento do eval funciona."""
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parents[1] / "tests"))
    from conftest import FakeLLM  # type: ignore

    import agent.llm as llm
    import agent.nodes.qualificador as q
    import agent.nodes.supervisor as s
    llm._modelo.cache_clear()
    for mod in (llm, q, s):
        for fn in ("llm_conversa", "llm_roteamento", "llm_analise"):
            if hasattr(mod, fn):
                setattr(mod, fn, lambda: FakeLLM())


def main() -> int:
    p = argparse.ArgumentParser(prog="evals", description="Harness de avaliação do agente")
    p.add_argument("--suite", choices=list(SUITES), action="append",
                   help="roda só esta suíte (pode repetir); padrão: todas")
    p.add_argument("-n", "--repeticoes", type=int, default=1,
                   help="execuções por caso — resposta de modelo varia; 3+ para medir dispersão")
    p.add_argument("--fake", action="store_true", help="LLM falso: valida o harness sem gastar token")
    p.add_argument("--limite-escape", type=float, default=0.0,
                   help="taxa de escape adversarial aceitável em %%; acima disso, sai com erro")
    p.add_argument("--limite-extracao", type=float, default=0.0,
                   help="acerto mínimo por campo na extração em %%; abaixo disso, sai com erro")
    args = p.parse_args()

    exigir_banco_de_teste()                      # nunca rodar contra o banco de dev
    if args.fake:
        _usar_llm_falso()

    inicio = datetime.now(timezone.utc)
    trechos = _trechos_do_prompt()
    resumos = []
    for nome in (args.suite or list(SUITES)):
        casos, fn = carregar(nome), SUITES[nome]
        print(f"rodando {nome}: {len(casos)} casos × {args.repeticoes}…", flush=True)
        execucoes = []
        for _ in range(args.repeticoes):
            rodada = []
            for caso in casos:
                try:
                    rodada.append(fn(caso, trechos) if nome == "adversarial" else fn(caso))
                except Exception:
                    from .casos import Resultado
                    rodada.append(Resultado(caso=caso.id, passou=False,
                                            detalhe=f"exceção: {traceback.format_exc(limit=1)[-120:]}"))
            execucoes.append(rodada)
        resumos.append(relatorio.resumir(nome, execucoes))

    custo = {} if args.fake else relatorio.custo_da_execucao(inicio)
    relatorio.imprimir(resumos, custo)
    caminho = relatorio.salvar(resumos, custo, "falso" if args.fake else os.getenv("SDR_MODEL_CONVERSA", "padrão"))
    print(f"\nresultado salvo em {caminho.relative_to(caminho.parents[2])}")

    # Limiares: o harness só reprova se você pedir. Sem limiar ele informa, não bloqueia — números
    # de LLM oscilam, e transformar oscilação em falha de build ensina o time a ignorar o build.
    falhou = False
    for r in resumos:
        if r["suite"] == "adversarial" and r.get("taxa_de_escape", 0) > args.limite_escape:
            print(f"\nREPROVADO: taxa de escape {r['taxa_de_escape']}% > limite {args.limite_escape}%")
            falhou = True
        if r["suite"] == "extracao" and args.limite_extracao and r.get("acerto_por_campo", 0) < args.limite_extracao:
            print(f"\nREPROVADO: acerto por campo {r['acerto_por_campo']}% < limite {args.limite_extracao}%")
            falhou = True
    return 1 if falhou else 0


if __name__ == "__main__":
    raise SystemExit(main())
