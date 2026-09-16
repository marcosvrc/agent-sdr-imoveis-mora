"""Porta de calendário: o que o agente precisa saber sobre a agenda de um corretor.

Duas perguntas, só. Quando está livre, e registre este compromisso. Tudo o que é específico do
Google fica no adaptador — o nó agendador nunca sabe qual calendário está do outro lado.
"""
from datetime import datetime
from typing import Protocol


class Calendario(Protocol):
    def ocupado(self, corretor_id: str, de: datetime, ate: datetime) -> list[tuple[datetime, datetime]]:
        """Intervalos já comprometidos do corretor. Lista vazia = agenda livre (ou desconhecida)."""
        ...

    def criar_evento(self, corretor_id: str, *, titulo: str, inicio: datetime, duracao_min: int,
                     descricao: str = "", local: str = "", convidados: list[str] | None = None) -> str | None:
        """Devolve o id do evento criado, ou None quando não há calendário conectado."""
        ...

    def cancelar_evento(self, corretor_id: str, evento_id: str) -> None: ...

    def conectado(self, corretor_id: str) -> bool: ...
