#!/usr/bin/env python3
"""Exporta a especificação OpenAPI da API para `docs/assets/openapi.json`.

Por que gravar em arquivo se o FastAPI já serve `/openapi.json`? Porque o portal de documentação é
estático (GitHub Pages) e não tem a API rodando atrás: sem o arquivo versionado, o Swagger da
documentação publicada só funcionaria para quem tivesse o backend de pé na própria máquina.

O arquivo é gerado, não escrito à mão — e a CI confere se está atualizado (`--verificar`), porque
especificação versionada que envelhece em silêncio é pior do que não ter especificação nenhuma.

    python scripts/gerar_openapi.py              # regrava o arquivo
    python scripts/gerar_openapi.py --verificar  # falha se estiver desatualizado (usado na CI)
"""
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "docs" / "assets" / "openapi.json"

# A app é importada só para extrair o esquema: nada de banco, nada de rede. O DSN precisa existir
# porque `get_settings()` roda no import; qualquer valor serve, nenhuma conexão é aberta.
os.environ.setdefault("SDR_DATABASE_DSN", "postgresql://sdr:sdr@localhost:5432/sdr")
os.environ.setdefault("SDR_PROFILE", "local")
sys.path[:0] = [str(RAIZ / "shared"), str(RAIZ / "services" / "api" / "src")]


def especificacao() -> str:
    from api.main import app
    spec = app.openapi()
    # `servers` não vem do FastAPI: é o que dá ao "Try it out" do Swagger um endereço para chamar.
    spec["servers"] = [
        {"url": "http://localhost:8000", "description": "Perfil local (docker compose)"},
        {"url": "https://api.exemplo.com.br", "description": "Perfil AWS — a confirmar no deploy"},
    ]
    # sort_keys: sem ordenação estável, cada geração produziria um diff diferente do anterior.
    return json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    novo = especificacao()
    if "--verificar" in sys.argv:
        atual = DESTINO.read_text(encoding="utf-8") if DESTINO.is_file() else ""
        if atual == novo:
            print(f"openapi.json em dia ({len(json.loads(novo)['paths'])} caminhos)")
            return 0
        print("openapi.json DESATUALIZADO — rode `make openapi` e faça commit do resultado.", file=sys.stderr)
        return 1
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(novo, encoding="utf-8")
    spec = json.loads(novo)
    operacoes = [op for ops in spec["paths"].values() for op in ops.values()]
    protegidas = sum(1 for op in operacoes if op.get("security"))
    print(f"{DESTINO.relative_to(RAIZ)}: {len(spec['paths'])} caminhos, "
          f"{len(operacoes)} operações ({protegidas} exigem autenticação)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
