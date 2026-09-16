"""Limite de vazão por lead: protege o orçamento de tokens e o serviço, sem calar o cliente.

Duas janelas, porque são dois abusos diferentes:
  - rajada: alguém segurando o Enter (ou um script) — muitas mensagens em segundos;
  - hora: uso sustentado muito acima do que uma conversa de verdade precisa.

Estourar não derruba a conversa: o turno é ignorado e, uma única vez por janela, o cliente recebe
um aviso. Bloquear em silêncio seria o mesmo defeito que já corrigimos — cliente esperando resposta.
"""
import time
from collections import deque
from threading import Lock

RAJADA_N, RAJADA_S = 5, 10          # 5 mensagens em 10s
HORA_N, HORA_S = 60, 3600           # 60 mensagens por hora
AVISO = ("Opa, chegaram muitas mensagens de uma vez e não consegui acompanhar. "
         "Me manda em uma mensagem só o que você procura?")

_janelas: dict[str, deque] = {}
_avisados: dict[str, float] = {}
_lock = Lock()


def _limpar_antigos(agora: float) -> None:
    """Sem isto, um processo de longa duração acumularia um deque por lead para sempre."""
    if len(_janelas) < 5000:
        return
    for lead_id in [k for k, v in _janelas.items() if not v or agora - v[-1] > HORA_S]:
        _janelas.pop(lead_id, None)
        _avisados.pop(lead_id, None)


def permitir(lead_id: str) -> tuple[bool, bool]:
    """Devolve (pode_processar, deve_avisar). O aviso sai no máximo uma vez por minuto por lead."""
    agora = time.monotonic()
    with _lock:
        _limpar_antigos(agora)
        marcas = _janelas.setdefault(lead_id, deque(maxlen=HORA_N + 1))
        while marcas and agora - marcas[0] > HORA_S:
            marcas.popleft()
        recentes = sum(1 for m in marcas if agora - m <= RAJADA_S)
        if recentes >= RAJADA_N or len(marcas) >= HORA_N:
            # mesmo cuidado do registro de acesso: num processo recém-iniciado, monotonic() é
            # pequeno e comparar com zero faria o primeiro aviso ser engolido
            ultimo = _avisados.get(lead_id)
            avisar = ultimo is None or agora - ultimo > 60
            if avisar:
                _avisados[lead_id] = agora
            return False, avisar
        marcas.append(agora)
        return True, False


def resetar() -> None:
    """Só para os testes: o estado é de processo."""
    with _lock:
        _janelas.clear()
        _avisados.clear()
