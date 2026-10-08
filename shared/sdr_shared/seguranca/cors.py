"""Origens que podem chamar a API e o canal web de outro endereço (CORS).

O padrão era `*` quando `SDR_CORS_ORIGINS` ficava vazio. Como a credencial do painel vai num
cabeçalho, e não num cookie, `*` deixava qualquer site aberto no navegador de quem usa o painel
chamar `http://localhost:8000` com o `dev-token` — e ler a resposta. Agora o vazio significa:

- perfil `local`: só os front-ends do compose (site 5173, painel 5174, CRM 3000);
- qualquer outro perfil: nenhuma origem externa (fail-closed). Produção declara as suas.
"""
from ..config import get_settings

ORIGENS_LOCAIS = tuple(f"http://{host}:{porta}" for porta in (5173, 5174, 3000)
                       for host in ("localhost", "127.0.0.1"))


def origens() -> list[str]:
    s = get_settings()
    declaradas = [o.strip() for o in (s.cors_origins or "").split(",") if o.strip()]
    if declaradas:
        return declaradas
    return list(ORIGENS_LOCAIS) if s.profile == "local" else []
