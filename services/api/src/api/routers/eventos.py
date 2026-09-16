"""Eventos de navegação do site (viewed_imovel, filtered, clicked_telegram) → contexto para a Mora."""
import re

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator
from sdr_shared.db import EventoNavegacaoRepository
from sdr_shared.seguranca import validar

router = APIRouter()
TIPOS = {"viewed_imovel", "filtered", "clicked_telegram", "opened_chat"}
# Endpoint público e sem sessão: o que entra aqui chega ao contexto do agente (imóveis vistos),
# então o formato é fechado — id de imóvel é id de imóvel, não texto livre.
ID_IMOVEL = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_CAMPOS, MAX_VALOR = 12, 200


class EventoNavegacao(BaseModel):
    session_id: str = Field(min_length=6, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    token: str | None = None
    tipo: str = Field(max_length=32)
    dados: dict = Field(default_factory=dict)

    @field_validator("dados")
    @classmethod
    def _fechar_o_formato(cls, v: dict) -> dict:
        if len(v) > MAX_CAMPOS:
            raise ValueError("evento com campos demais")
        limpo = {}
        for chave, valor in v.items():
            if not isinstance(chave, str) or len(chave) > 40:
                continue
            if chave == "imovel_id":
                if not (isinstance(valor, str) and ID_IMOVEL.match(valor)):
                    raise ValueError("imovel_id inválido")
                limpo[chave] = valor
            elif isinstance(valor, (str, int, float, bool)) or valor is None:
                limpo[chave] = str(valor)[:MAX_VALOR] if isinstance(valor, str) else valor
        return limpo


@router.post("", status_code=202)
def registrar(ev: EventoNavegacao):
    if not validar(ev.session_id, ev.token):
        return {"ok": True}          # descarta em silêncio: é telemetria, não vale devolver erro a um bot
    if ev.tipo in TIPOS:
        EventoNavegacaoRepository().registrar(ev.session_id, ev.tipo, ev.dados)
    return {"ok": True}
