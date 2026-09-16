"""Conexão da agenda do corretor com o Google.

O corretor clica em conectar, autoriza no Google e volta. Guardamos só o refresh token, e ele
nunca volta para o painel — a tela só pergunta se está conectado ou não.
"""
import logging
from html import escape

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sdr_shared.config import get_settings
from sdr_shared.db import CorretorRepository, auditar
from sdr_shared.seguranca import oauth
from ..auth import corretor_atual

log = logging.getLogger("api.calendario")
router = APIRouter()


def _adaptador():
    s = get_settings()
    if not (s.google_client_id and s.google_client_secret):
        raise HTTPException(503, "Google Calendar não configurado: defina SDR_GOOGLE_CLIENT_ID e SDR_GOOGLE_CLIENT_SECRET")
    from sdr_shared.adapters.google.calendario import CalendarioGoogle
    return CalendarioGoogle


@router.get("/status", dependencies=[Depends(corretor_atual)])
def status():
    """O painel usa isto para saber quem já conectou. Nenhum token sai daqui."""
    s = get_settings()
    repo = CorretorRepository()
    return {"disponivel": bool(s.google_client_id and s.google_client_secret),
            "corretores": {c.id: bool(repo.credencial_calendario(c.id)) for c in repo.listar()}}


@router.post("/conectar/{corretor_id}", dependencies=[Depends(corretor_atual)])
def conectar(corretor_id: str):
    """Devolve a URL de consentimento. Quem abre é o navegador do corretor, não a API."""
    if not CorretorRepository().get(corretor_id):
        raise HTTPException(404, "corretor não encontrado")
    s = get_settings()
    return {"url": _adaptador().url_de_autorizacao(corretor_id, s.google_redirect_uri)}


@router.get("/callback", response_class=HTMLResponse)
def callback(code: str | None = None, state: str | None = None, error: str | None = None):
    """Volta do Google. Endpoint público por definição — quem chama é o navegador, sem o nosso token.
    O `state` é assinado por nós (ver seguranca/oauth.py): sem isso, bastava adivinhar o id de um
    corretor para plantar a credencial da PRÓPRIA conta Google na agenda dele."""
    if error or not code or not state:
        return _pagina("Não foi possível conectar", f"O Google respondeu: {error or 'autorização incompleta'}.", False)
    corretor_id = oauth.validar(state)
    if not corretor_id:
        return _pagina("Link expirado", "Este link de conexão não é válido ou passou do prazo. "
                                        "Volte ao painel e clique em conectar novamente.", False)
    if not CorretorRepository().get(corretor_id):
        return _pagina("Corretor não encontrado", "O link de conexão não corresponde a um corretor ativo.", False)

    refresh = _adaptador().trocar_codigo(code, get_settings().google_redirect_uri)
    if not refresh:
        # Sem refresh token não adianta guardar nada: acontece quando o corretor já autorizou antes
        # e o Google não reemite. Reautorizar com prompt=consent resolve.
        return _pagina("Autorização incompleta", "O Google não devolveu uma credencial de longa duração. "
                                                 "Tente conectar novamente.", False)
    CorretorRepository().salvar_credencial_calendario(corretor_id, refresh)
    auditar(acao="corretor.calendario_conectado", entidade="corretor", entidade_id=corretor_id,
            ator_tipo="corretor", ator_id=corretor_id, dados={"provedor": "google"})
    return _pagina("Agenda conectada", "Suas visitas passam a aparecer no seu Google Agenda, e a Mora "
                                       "não vai mais oferecer horários em que você já tem compromisso.", True)


@router.delete("/{corretor_id}", status_code=204)
def desconectar(corretor_id: str, ator: dict = Depends(corretor_atual)):
    CorretorRepository().salvar_credencial_calendario(corretor_id, None)
    auditar(acao="corretor.calendario_desconectado", entidade="corretor", entidade_id=corretor_id,
            ator_tipo="corretor", ator_id=ator.get("id"), ator_nome=ator.get("email"))


def _pagina(titulo: str, texto: str, ok: bool) -> HTMLResponse:
    # escape(): esta página exibe texto vindo da querystring do Google (o parâmetro `error`), e o
    # endpoint é público. Sem escapar, `?error=<img src=x onerror=...>` executaria no navegador de
    # quem abrisse o link — XSS refletido num domínio nosso.
    titulo, texto = escape(titulo), escape(texto)
    cor = "#0f766e" if ok else "#b45309"
    return HTMLResponse(f"""<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{titulo} — Mora</title>
<body style="margin:0;display:grid;place-items:center;min-height:100vh;background:#f6f7f6;
             font-family:system-ui,-apple-system,'Segoe UI',sans-serif;color:#15201b">
  <main style="max-width:32rem;padding:2rem;text-align:center">
    <div style="font-size:2.5rem">{'✓' if ok else '!'}</div>
    <h1 style="font-size:1.35rem;margin:.5rem 0;color:{cor}">{titulo}</h1>
    <p style="color:#5b6b64;line-height:1.6">{texto}</p>
    <p style="color:#8a958f;font-size:.85rem;margin-top:2rem">Pode fechar esta aba.</p>
  </main>
</body></html>""")
