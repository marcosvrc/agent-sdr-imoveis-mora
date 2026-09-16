"""Google Calendar do corretor.

Cada corretor conecta a própria agenda uma vez (OAuth); guardamos só o refresh token, que é o que
permite agir depois sem ele estar presente. A regra que atravessa este arquivo: **falha do Google
nunca derruba o agendamento**. Se a API não responde, a visita continua sendo marcada no nosso
banco — o cliente não pode perder a visita porque um token expirou.

Usa a API REST direta (httpx) em vez do google-api-python-client: são quatro chamadas, e evitamos
arrastar uma dependência pesada para dentro do Lambda.
"""
import logging
from datetime import datetime, timedelta, timezone

import httpx

from ...config import get_settings

log = logging.getLogger("sdr.calendario.google")

TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/calendar/v3"
AUTORIZACAO = "https://accounts.google.com/o/oauth2/v2/auth"
# Mínimo necessário: ler ocupação e escrever os eventos que nós criamos.
ESCOPOS = ["https://www.googleapis.com/auth/calendar.events",
           "https://www.googleapis.com/auth/calendar.freebusy"]
TIMEOUT = 8.0            # o cliente está esperando resposta; não dá para ficar pendurado no Google


class CalendarioGoogle:
    def __init__(self) -> None:
        self._tokens: dict[str, tuple[str, datetime]] = {}     # corretor_id → (access_token, validade)

    # ---------- credenciais ----------

    def conectado(self, corretor_id: str | None) -> bool:
        return bool(corretor_id) and bool(self._refresh_token(corretor_id))

    def _refresh_token(self, corretor_id: str) -> str | None:
        from ...db.painel import CorretorRepository
        try:
            return CorretorRepository().credencial_calendario(corretor_id)
        except Exception:
            log.exception("falha ao ler a credencial de calendário do corretor %s", corretor_id)
            return None

    def _access_token(self, corretor_id: str) -> str | None:
        """Access token dura uma hora; trocamos o refresh por um novo quando o cache vence."""
        token, validade = self._tokens.get(corretor_id, (None, datetime.min.replace(tzinfo=timezone.utc)))
        if token and validade > datetime.now(timezone.utc) + timedelta(seconds=60):
            return token
        refresh = self._refresh_token(corretor_id)
        if not refresh:
            return None
        s = get_settings()
        try:
            r = httpx.post(TOKEN_URL, timeout=TIMEOUT, data={
                "client_id": s.google_client_id, "client_secret": s.google_client_secret,
                "refresh_token": refresh, "grant_type": "refresh_token"})
            if r.status_code == 400:
                # consentimento revogado pelo corretor: desconecta em vez de tentar de novo a cada visita
                log.warning("credencial de calendário do corretor %s foi revogada", corretor_id)
                self._desconectar(corretor_id)
                return None
            r.raise_for_status()
            dados = r.json()
        except Exception:
            log.exception("falha ao renovar o token de calendário do corretor %s", corretor_id)
            return None
        token = dados["access_token"]
        self._tokens[corretor_id] = (token, datetime.now(timezone.utc) + timedelta(seconds=int(dados.get("expires_in", 3600))))
        return token

    def _desconectar(self, corretor_id: str) -> None:
        from ...db.painel import CorretorRepository
        try:
            CorretorRepository().salvar_credencial_calendario(corretor_id, None)
        except Exception:
            log.exception("falha ao desconectar o calendário do corretor %s", corretor_id)
        self._tokens.pop(corretor_id, None)

    # ---------- agenda ----------

    def ocupado(self, corretor_id: str, de: datetime, ate: datetime) -> list[tuple[datetime, datetime]]:
        """Ocupação do Google somada à das nossas visitas.

        As duas fontes importam: o corretor pode ter almoço marcado no Google e visita marcada aqui.
        Sem o Google (ou com ele fora do ar), devolve só a nossa — a oferta fica mais larga, nunca
        errada a ponto de marcar em cima de uma visita que já existe no sistema.
        """
        from ...db import VisitaRepository
        nossa = VisitaRepository().ocupacao_do_corretor(corretor_id, de, ate)
        token = self._access_token(corretor_id)
        if not token:
            return nossa
        try:
            r = httpx.post(f"{API}/freeBusy", timeout=TIMEOUT,
                           headers={"Authorization": f"Bearer {token}"},
                           json={"timeMin": de.isoformat(), "timeMax": ate.isoformat(),
                                 "timeZone": "UTC", "items": [{"id": "primary"}]})
            r.raise_for_status()
            blocos = r.json()["calendars"]["primary"].get("busy", [])
        except Exception:
            log.exception("free/busy do corretor %s falhou — usando só a agenda interna", corretor_id)
            return nossa
        return nossa + [(_dt(b["start"]), _dt(b["end"])) for b in blocos]

    def criar_evento(self, corretor_id: str, *, titulo: str, inicio: datetime, duracao_min: int,
                     descricao: str = "", local: str = "", convidados: list[str] | None = None) -> str | None:
        token = self._access_token(corretor_id)
        if not token:
            return None
        corpo = {
            "summary": titulo,
            "description": descricao,
            "location": local,
            "start": {"dateTime": inicio.isoformat(), "timeZone": "America/Sao_Paulo"},
            "end": {"dateTime": (inicio + timedelta(minutes=duracao_min)).isoformat(), "timeZone": "America/Sao_Paulo"},
            "attendees": [{"email": e} for e in (convidados or []) if e],
            "reminders": {"useDefault": False,
                          "overrides": [{"method": "popup", "minutes": 60}, {"method": "email", "minutes": 24 * 60}]},
        }
        try:
            r = httpx.post(f"{API}/calendars/primary/events", timeout=TIMEOUT,
                           headers={"Authorization": f"Bearer {token}"},
                           params={"sendUpdates": "all"},          # o cliente recebe o convite por e-mail
                           json=corpo)
            r.raise_for_status()
            return r.json().get("id")
        except Exception:
            log.exception("não consegui criar o evento do corretor %s no Google — a visita segue no sistema", corretor_id)
            return None

    def cancelar_evento(self, corretor_id: str, evento_id: str) -> None:
        token = self._access_token(corretor_id)
        if not token or not evento_id:
            return
        try:
            r = httpx.delete(f"{API}/calendars/primary/events/{evento_id}", timeout=TIMEOUT,
                             headers={"Authorization": f"Bearer {token}"}, params={"sendUpdates": "all"})
            if r.status_code not in (200, 204, 404, 410):          # 404/410: já não existe, tudo bem
                r.raise_for_status()
        except Exception:
            log.exception("falha ao cancelar o evento %s do corretor %s", evento_id, corretor_id)

    # ---------- consentimento ----------

    @staticmethod
    def url_de_autorizacao(corretor_id: str, redirect_uri: str) -> str:
        s = get_settings()
        from urllib.parse import urlencode
        from ...seguranca import oauth
        # `state` assinado e com prazo: é o que impede alguém de adivinhar o id de um corretor e
        # ligar a própria conta Google à agenda dele (ver seguranca/oauth.py).
        return AUTORIZACAO + "?" + urlencode({
            "client_id": s.google_client_id, "redirect_uri": redirect_uri, "response_type": "code",
            "scope": " ".join(ESCOPOS), "access_type": "offline", "prompt": "consent",
            "include_granted_scopes": "true", "state": oauth.assinar(corretor_id)})

    @staticmethod
    def trocar_codigo(codigo: str, redirect_uri: str) -> str | None:
        """Troca o código do consentimento pelo refresh token — o único que guardamos."""
        s = get_settings()
        try:
            r = httpx.post(TOKEN_URL, timeout=TIMEOUT, data={
                "client_id": s.google_client_id, "client_secret": s.google_client_secret,
                "code": codigo, "grant_type": "authorization_code", "redirect_uri": redirect_uri})
            r.raise_for_status()
            return r.json().get("refresh_token")
        except Exception:
            log.exception("falha ao trocar o código de autorização do Google")
            return None


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))
