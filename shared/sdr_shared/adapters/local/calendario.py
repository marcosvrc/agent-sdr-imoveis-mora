"""Agenda sem calendário externo: o banco é a única fonte de ocupação.

É o comportamento que a Mora sempre teve, agora atrás da porta. Continua valendo para qualquer
corretor que não tenha conectado o Google — e é o que roda na demonstração.
"""
from datetime import datetime


class CalendarioLocal:
    def ocupado(self, corretor_id: str, de: datetime, ate: datetime) -> list[tuple[datetime, datetime]]:
        from ...db import VisitaRepository
        return VisitaRepository().ocupacao_do_corretor(corretor_id, de, ate)

    def criar_evento(self, corretor_id: str, *, titulo: str, inicio: datetime, duracao_min: int,
                     descricao: str = "", local: str = "", convidados: list[str] | None = None) -> str | None:
        return None          # a visita já está no nosso banco; não há outro lugar para escrever

    def cancelar_evento(self, corretor_id: str, evento_id: str) -> None:
        return None

    def conectado(self, corretor_id: str) -> bool:
        return False
