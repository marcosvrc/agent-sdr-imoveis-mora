"""Regera todos os diagramas. Use `make diagramas` na raiz do repositório."""
import importlib
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from base import gerar  # noqa: E402

MODULOS = ["d01_macro", "d02_contexto", "d03_estados_negocio", "d04_estados_codigo",
           "d05_mensageria", "d06_crm_publicacao", "d07_busca", "d08_topologia",
           "d09_turno", "d10_supervisor"]


def main() -> None:
    destino = sys.argv[1] if len(sys.argv) > 1 else "docs/assets/diagramas"
    total = 0
    for nome in MODULOS:
        mod = importlib.import_module(nome)
        for caminho in gerar(mod.montar(), destino):
            total += 1
    print(f"{total} diagramas em {destino}/")


if __name__ == "__main__":
    main()
