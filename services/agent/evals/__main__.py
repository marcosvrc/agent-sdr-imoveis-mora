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

    import importlib

    import agent.llm as llm
    from agent.graph import ESPECIALISTAS
    llm._modelo.cache_clear()
    # Derivada de ESPECIALISTAS, e não escrita à mão. Os nós fazem `from ..llm import llm_conversa`,
    # então trocar a função no módulo `llm` NÃO alcança quem já importou o nome — um especialista
    # novo continuaria chamando o modelo de verdade no modo falso, e a conta apareceria na fatura
    # sem nenhum sinal no terminal. A mesma lista à mão já mordeu duas vezes neste projeto.
    modulos = [llm] + [importlib.import_module(f"agent.nodes.{n}")
                       for n in (*ESPECIALISTAS, "supervisor")]
    for mod in modulos:
        for fn in ("llm_conversa", "llm_roteamento", "llm_analise"):
            if hasattr(mod, fn):
                setattr(mod, fn, lambda: FakeLLM())


def _usar_embedder_falso() -> None:
    """Embedder determinístico, saco de palavras. Serve para o harness do RAG rodar sem Ollama.

    Os números que ele produz NÃO dizem nada sobre a qualidade semântica — "fiador" e "avalista"
    ficam distantes onde um modelo real os aproximaria. O que ele prova é que o encanamento
    funciona: indexação, SQL vetorial, ordenação, piso e o caminho da abstenção. Serve de teste de
    regressão do harness; não serve de baseline.

    É de TRIGRAMAS de caractere, e não de palavras inteiras, por um motivo prático: o dataset foi
    escrito de propósito sem repetir o vocabulário dos cabeçalhos, então um saco de palavras acerta
    zero e um número que é sempre zero não detecta regressão nenhuma. Trigrama pega parentesco
    morfológico ("alugar"/"aluguel", "visita"/"visitar") e produz um número baixo mas sensível: se
    alguém subir o piso para 0,9 ou quebrar a ordenação, ele cai e o CI reclama.
    """
    import hashlib
    import math

    import sdr_shared.ports as ports

    dim = 1024

    def embed(texto: str) -> list[float]:
        limpo = " " + "".join(c.lower() if c.isalnum() else " " for c in texto).strip() + " "
        vetor = [0.0] * dim
        for i in range(len(limpo) - 2):
            tri = limpo[i:i + 3]
            if tri.strip():
                vetor[int(hashlib.sha256(tri.encode()).hexdigest()[:8], 16) % dim] += 1.0
        norma = math.sqrt(sum(x * x for x in vetor)) or 1.0
        return [x / norma for x in vetor]

    falso = type("EmbedderFalso", (), {"dimensoes": dim, "embed": staticmethod(embed)})()
    ports.get_embedder.cache_clear()
    ports.get_embedder = lambda: falso


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
    p.add_argument("--limite-abstencao", type=float, default=0.0,
                   help="abstenção mínima nas negativas ÓBVIAS do RAG em %%; abaixo disso, sai com "
                        "erro. Só as óbvias: as adjacentes são decisão de produto, não regressão")
    args = p.parse_args()

    exigir_banco_de_teste()                      # nunca rodar contra o banco de dev
    if args.fake:
        _usar_llm_falso()
        _usar_embedder_falso()

    inicio = datetime.now(timezone.utc)
    trechos = _trechos_do_prompt()
    resumos = []
    for nome in (args.suite or list(SUITES)):
        casos, fn = carregar(nome), SUITES[nome]
        if nome == "rag":
            from .suites import indexar_corpus
            print("  indexando o corpus institucional com o embedder em uso…", flush=True)
            print(f"  {indexar_corpus()} trechos indexados", flush=True)
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
    # Exceção num caso não é "reprovado", é harness quebrado — e some no meio de uma taxa de
    # aprovação baixa. Reprova sempre, independentemente de limiar pedido.
    quebrados = [(r["suite"], c["caso"]) for r in resumos for c in r["detalhes"]
                 if c["detalhe"].startswith("exceção:")]
    if quebrados:
        print(f"\nREPROVADO: {len(quebrados)} caso(s) levantaram exceção — "
              f"{', '.join(f'{s}/{c}' for s, c in quebrados[:5])}")
        falhou = True

    for r in resumos:
        if r["suite"] == "adversarial" and r.get("taxa_de_escape", 0) > args.limite_escape:
            print(f"\nREPROVADO: taxa de escape {r['taxa_de_escape']}% > limite {args.limite_escape}%")
            falhou = True
        if r["suite"] == "rag" and args.limite_abstencao and r.get("abstencao_obvia", 0) < args.limite_abstencao:
            print(f"\nREPROVADO: abstenção {r['abstencao_obvia']}% < limite {args.limite_abstencao}%")
            falhou = True
        if r["suite"] == "extracao" and args.limite_extracao and r.get("acerto_por_campo", 0) < args.limite_extracao:
            print(f"\nREPROVADO: acerto por campo {r['acerto_por_campo']}% < limite {args.limite_extracao}%")
            falhou = True
    return 1 if falhou else 0


if __name__ == "__main__":
    raise SystemExit(main())
