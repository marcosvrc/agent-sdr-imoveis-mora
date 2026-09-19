from typing import Protocol
from collections.abc import Callable


class Broker(Protocol):
    """Fila por tópico com ordem garantida por chave (lead_id)."""
    def publish(self, topic: str, body: str, key: str) -> None: ...
    def consume(self, topic: str, handler: Callable[[str], None]) -> None:
        """Loop bloqueante: o worker do serviço fica aqui consumindo a fila."""
        ...
