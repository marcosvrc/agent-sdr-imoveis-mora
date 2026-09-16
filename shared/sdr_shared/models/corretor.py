from datetime import datetime
from pydantic import BaseModel, Field


class Corretor(BaseModel):
    id: str
    nome: str
    email: str | None = None
    telefone: str | None = None
    regioes: list[str] = Field(default_factory=list)   # zona_sul, zona_oeste...
    ativo: bool = True
    foto: str | None = None          # data:image/...;base64 (≤ 300 KB) ou URL
    criado_em: datetime | None = None
