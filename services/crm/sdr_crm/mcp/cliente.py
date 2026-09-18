"""Cliente HTTP do adaptador MCP.

O servidor MCP **não fala com o banco** — ele traduz ferramenta em chamada REST (seção 3). É o que
garante que as duas portas de entrada tenham as mesmas regras: se o MCP escrevesse direto, um dia
uma validação existiria só na API e o agente passaria por baixo dela.

Três decisões que a seção 11 obriga e que são fáceis de errar:

1. **Timeout de 10 s.** Um agente conversando não pode ficar pendurado.
2. **No máximo duas novas tentativas, com backoff e jitter — e só em falha transitória.**
3. **PUT e PATCH nunca são repetidos automaticamente.** Eles não têm chave de idempotência; repetir
   às cegas depois de um timeout pode aplicar a mesma alteração duas vezes sobre versões
   diferentes. Depois de um resultado incerto, o caminho é consultar o recurso e reconciliar.

O token vem de `CRM_API_TOKEN` no ambiente e **nunca** é argumento de ferramenta: argumento aparece
no log do cliente, no histórico da conversa e no prompt do modelo.
"""
import os
import random
import time

import httpx

TIMEOUT = 10.0
TENTATIVAS = 3                      # 1 original + 2 novas
TRANSITORIOS = frozenset({429, 502, 503, 504})
SEM_RETRY = frozenset({"PUT", "PATCH"})


class RespostaCRM:
    def __init__(self, status: int, corpo: dict, request_id: str = "") -> None:
        self.status = status
        self.corpo = corpo
        self.request_id = request_id or corpo.get("request_id", "")

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    @property
    def erro(self) -> dict:
        e = (self.corpo or {}).get("error") or {}
        return {"code": e.get("code", f"HTTP_{self.status}"),
                "message": e.get("message", "Falha na chamada ao CRM."),
                "details": e.get("details", {}),
                "retryable": bool(e.get("retryable", self.status in TRANSITORIOS))}


class ClienteCRM:
    def __init__(self, base_url: str | None = None, token: str | None = None) -> None:
        self.base_url = (base_url or os.environ.get("CRM_API_BASE_URL", "http://localhost:8100")).rstrip("/")
        self.token = token or os.environ.get("CRM_API_TOKEN", "")
        self._http = httpx.Client(timeout=TIMEOUT, base_url=self.base_url)

    def chamar(self, metodo: str, rota: str, *, params: dict | None = None,
               corpo: dict | None = None, operation_id: str | None = None,
               expected_version: int | None = None) -> RespostaCRM:
        """`operation_id` vira `Idempotency-Key`; `expected_version` vira `If-Match`.

        A chave é a MESMA em todas as tentativas — é isso que faz o retry ser seguro. Gerar uma
        chave nova a cada tentativa transformaria a proteção em duplicata garantida.
        """
        cabecalhos = {"Authorization": f"Bearer {self.token}"}
        if operation_id:
            cabecalhos["Idempotency-Key"] = operation_id
        if expected_version is not None:
            cabecalhos["If-Match"] = f'"{expected_version}"'

        ultima: Exception | None = None
        for tentativa in range(TENTATIVAS):
            try:
                r = self._http.request(metodo, rota, params=params, json=corpo, headers=cabecalhos)
            except httpx.RequestError as exc:
                ultima = exc
                if metodo.upper() in SEM_RETRY or tentativa == TENTATIVAS - 1:
                    break
                self._esperar(tentativa)
                continue

            if r.status_code in TRANSITORIOS and metodo.upper() not in SEM_RETRY \
                    and tentativa < TENTATIVAS - 1:
                self._esperar(tentativa, r.headers.get("Retry-After"))
                continue
            try:
                corpo_resposta = r.json()
            except ValueError:
                corpo_resposta = {}
            return RespostaCRM(r.status_code, corpo_resposta)

        # Resultado INCERTO: a chamada pode ter sido aplicada do outro lado. Nunca anunciar sucesso
        # aqui (seção 11) — quem chama precisa consultar o recurso antes de tentar de novo.
        return RespostaCRM(503, {"error": {
            "code": "CRM_UNREACHABLE",
            "message": ("Não foi possível falar com o CRM; o resultado é incerto. "
                        "Consulte o recurso antes de repetir a operação."),
            "details": {"causa": type(ultima).__name__ if ultima else "resposta transitória"},
            "retryable": True}})

    @staticmethod
    def _esperar(tentativa: int, retry_after: str | None = None) -> None:
        """Backoff exponencial com jitter. O jitter existe para que dois workers que caíram no
        mesmo segundo não voltem juntos e derrubem o CRM de novo."""
        if retry_after and retry_after.isdigit():
            time.sleep(min(int(retry_after), 5))
            return
        time.sleep((0.25 * (2 ** tentativa)) + random.uniform(0, 0.25))

    def fechar(self) -> None:
        self._http.close()
