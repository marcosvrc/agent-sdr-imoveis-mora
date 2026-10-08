from typing import Protocol
from collections.abc import Callable


class BarramentoIndisponivel(RuntimeError):
    """O barramento não responde: o turno não começou e a mensagem tem de ficar pendente na fila.

    Não é falha do atendimento — é infraestrutura. Quem consome NÃO chama o caminho de falha (que
    avisa o cliente e encaminha ao corretor) nem confirma a mensagem: ela é retomada quando o
    barramento volta. Encaminhar ao corretor por causa de um Redis reiniciando punia o cliente pelo
    problema de outra pessoa."""


class Broker(Protocol):
    """Fila por tópico com ordem garantida por chave (lead_id)."""
    def publish(self, topic: str, body: str, key: str) -> None: ...
    def consume(self, topic: str, handler: Callable[[str], None]) -> None:
        """Loop bloqueante: o worker do serviço fica aqui consumindo a fila."""
        ...
