"""Lista as dependências de TERCEIROS da imagem Python, lidas dos pyproject.toml.

Existe para o Dockerfile.python instalar as dependências numa camada que só muda quando um
pyproject muda. Antes o `pip install -e` vinha depois de `COPY shared services`, e qualquer edição
num .py invalidava a camada: cada `--build` reinstalava tudo, inclusive o faster-whisper e o
ctranslate2, que são as centenas de MB mais lentas da imagem.

A fonte da verdade continua sendo cada pyproject — nada de requirements.txt paralelo para
envelhecer. Os pacotes do próprio monorepo (`sdr-*`) ficam de fora: entram depois, editáveis e
sem dependências, quando o código já foi copiado.

Uso (dentro do build): python dependencias.py /app > requisitos.txt
"""
import sys
import tomllib
from pathlib import Path

# Pasta → extras instalados; mudar aqui é mudar o que existe dentro dos containers. Os extras `dev`
# trazem o pytest: sem eles `make test-docker` — o caminho de quem não tem Python 3.12 no host —
# morria com "No module named pytest". São poucos MB perto do whisper.
ALVOS = {
    "shared": ["local", "openai"],
    "services/agent": ["local", "dev"],   # faster-whisper: sem ele, áudio vira "(áudio não compreendido)"
    "services/api": ["dev"],
    "services/channels/telegram": [],
    "services/channels/local": [],        # fastapi, uvicorn[standard], websockets — com versão mínima
    "services/scheduler": [],
    "services/ingestion": [],
    "services/crm": ["mcp", "dev"],
}


def dependencias(raiz: Path) -> list[str]:
    deps: set[str] = set()
    for pasta, extras in ALVOS.items():
        projeto = tomllib.loads((raiz / pasta / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        deps.update(projeto.get("dependencies", []))
        for extra in extras:
            deps.update(projeto["optional-dependencies"][extra])
    return sorted(d for d in deps if not d.replace("_", "-").lower().startswith("sdr-"))


if __name__ == "__main__":
    print("\n".join(dependencias(Path(sys.argv[1] if len(sys.argv) > 1 else "."))))
