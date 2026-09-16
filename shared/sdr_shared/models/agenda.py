from datetime import datetime
from pydantic import BaseModel


class Visita(BaseModel):
    id: str
    lead_id: str
    imovel_id: str | None = None
    tipo: str                # visita | reuniao_especialista
    inicio: datetime
    corretor_id: str | None = None
    status: str = "confirmada"
