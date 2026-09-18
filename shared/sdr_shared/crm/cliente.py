"""Cliente HTTP do CRM, do lado da Mora.

Parecido com o adaptador do servidor MCP, e separado dele de propósito: aquele mora dentro do CRM e
existe para o agente EXTERNO; este mora na Mora e existe para o agente DELA. Compartilhar o módulo
criaria uma dependência de `sdr_shared` para `sdr_crm` — exatamente o acoplamento que a decisão
D-01 evita.

Sem CRM configurado (`SDR_CRM_URL` vazio), tudo aqui vira no-op silencioso. É o que mantém o
`make local-ollama` de sempre funcionando sem subir mais um serviço.
"""
import logging
import os
from typing import Any

import httpx

log = logging.getLogger("crm")

TIMEOUT = 5.0            # metade do timeout do adaptador MCP: aqui há um cliente esperando resposta
TRANSITORIOS = frozenset({429, 502, 503, 504})


def habilitado() -> bool:
    """Exige URL **e** token.

    Só a URL não basta: no compose ela tem um padrão (`http://crm-api:8100`), e sem token cada
    turno viraria um 401 no log de quem nunca pediu a integração. "Configurado" é ter os dois.
    """
    return bool(os.environ.get("SDR_CRM_URL", "").strip()
                and os.environ.get("SDR_CRM_TOKEN", "").strip())


class RespostaCRM:
    def __init__(self, status: int, corpo: dict[str, Any]) -> None:
        self.status = status
        self.corpo = corpo or {}

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    @property
    def dados(self) -> dict:
        return self.corpo.get("data") or {}

    @property
    def codigo(self) -> str:
        return ((self.corpo.get("error") or {}).get("code")) or f"HTTP_{self.status}"

    @property
    def mensagem(self) -> str:
        return ((self.corpo.get("error") or {}).get("message")) or ""


class ClienteCRM:
    """Uma chamada, uma tentativa.

    Sem retry aqui de propósito: quem chama é o turno do agente, com o cliente esperando do outro
    lado. Repetir uma chamada lenta gasta o tempo do cliente para melhorar um registro que ele nem
    vê. O que protege contra a perda é a `Idempotency-Key`: a mesma ação lógica pode ser publicada
    de novo no turno seguinte sem duplicar nada.
    """

    def __init__(self, base_url: str | None = None, token: str | None = None) -> None:
        self.base_url = (base_url or os.environ.get("SDR_CRM_URL", "")).rstrip("/")
        self.token = token or os.environ.get("SDR_CRM_TOKEN", "")
        self._http: httpx.Client | None = None

    @property
    def http(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(timeout=TIMEOUT, base_url=self.base_url)
        return self._http

    def chamar(self, metodo: str, rota: str, *, params: dict | None = None,
               corpo: dict | None = None, operation_id: str | None = None,
               versao: int | None = None) -> RespostaCRM:
        cabecalhos = {"Authorization": f"Bearer {self.token}"}
        if operation_id:
            cabecalhos["Idempotency-Key"] = operation_id
        if versao is not None:
            cabecalhos["If-Match"] = f'"{versao}"'
        try:
            r = self.http.request(metodo, rota, params=params, json=corpo, headers=cabecalhos)
        except httpx.RequestError as exc:
            log.warning("CRM inacessível em %s %s: %s", metodo, rota, type(exc).__name__)
            return RespostaCRM(503, {"error": {"code": "CRM_UNREACHABLE",
                                               "message": str(exc)[:200]}})
        try:
            corpo_resposta = r.json()
        except ValueError:
            corpo_resposta = {}
        if not (200 <= r.status_code < 300):
            # `info`, não `error`: uma recusa do CRM costuma ser a regra de negócio funcionando
            # (contato bloqueado, atendimento humano), e não uma falha do sistema.
            log.info("CRM recusou %s %s: %s", metodo, rota,
                     (corpo_resposta.get("error") or {}).get("code"))
        return RespostaCRM(r.status_code, corpo_resposta)
