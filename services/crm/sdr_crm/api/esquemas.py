"""Corpos de requisição.

`extra="forbid"` em todos, como a seção 7 exige. O motivo prático: um agente que escreve
`budget_max` em vez de `budget_max_cents` precisa receber 422 — e não um 200 silencioso que grava
preferências sem orçamento e só aparece três passos depois, quando a qualificação falha por um
campo que o agente jura ter enviado.
"""
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Centavos = Annotated[int, Field(ge=0, le=10**12)]


class Corpo(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Corpo):
    email: str
    password: str


class LeadNovo(Corpo):
    name: str = Field(min_length=1, max_length=200)
    source: str = Field(min_length=1, max_length=60)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    external_contact_id: str | None = Field(default=None, max_length=120)
    contact_policy: Literal["unknown", "allowed", "blocked"] = "unknown"
    synthetic: bool = True

    @model_validator(mode="after")
    def exige_identificador(self):
        if not (self.email or self.phone or self.external_contact_id):
            raise ValueError("informe email, phone ou external_contact_id — nome não identifica pessoa")
        return self


class LeadAlteracao(Corpo):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    # Desligar o contato é permitido ao agente; religar, não (seção 4). A regra está na rota,
    # porque depende de QUEM está chamando.
    contact_policy: Literal["unknown", "allowed", "blocked"] | None = None
    archived: bool | None = None


class OportunidadeNova(Corpo):
    lead_id: str
    purpose: Literal["rent", "buy"]
    owner_id: str | None = None


class Preferencias(Corpo):
    """PUT: substituição COMPLETA. Campo omitido vira vazio/nulo — está no contrato da seção 7.

    Substituir em vez de mesclar é a escolha certa aqui porque o agente reconstrói as preferências
    a cada turno a partir da conversa inteira. Com merge, uma exigência que o cliente retirou
    ("não precisa mais de vaga") ficaria para sempre, sem nenhuma forma de removê-la.
    """

    city: str | None = Field(default=None, max_length=120)
    neighborhoods: list[str] = Field(default_factory=list, max_length=20)
    property_types: list[str] = Field(default_factory=list, max_length=10)
    budget_min_cents: Centavos | None = None
    budget_max_cents: Centavos | None = None
    budget_basis: Literal["base_price", "monthly_total"] = "base_price"
    bedrooms_min: int | None = Field(default=None, ge=0, le=20)
    parking_min: int | None = Field(default=None, ge=0, le=20)
    move_by: date | None = None
    requirements: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def orcamento_coerente(self):
        if (self.budget_min_cents is not None and self.budget_max_cents is not None
                and self.budget_min_cents > self.budget_max_cents):
            raise ValueError("budget_min_cents não pode ser maior que budget_max_cents")
        return self


class Transicao(Corpo):
    target_stage: Literal["new", "in_service", "qualified", "visit_scheduled",
                          "negotiation", "won", "lost"]
    reason: str | None = Field(default=None, max_length=500)


class Interesse(Corpo):
    status: Literal["presented", "interested", "rejected"]
    notes: str | None = Field(default=None, max_length=1000)


class InteracaoNova(Corpo):
    channel: str = Field(min_length=1, max_length=40)
    direction: Literal["inbound", "outbound", "internal"]
    summary: str = Field(min_length=1, max_length=4000)
    occurred_at: datetime
    opportunity_id: str | None = None
    external_event_id: str | None = Field(default=None, max_length=200)


def _conferir_fotos(obj):
    """A mesma URL duas vezes na lista enviada é engano de colagem, e é problema do PAYLOAD — por
    isso 422 aqui, e não o 409 de conflito com o que já está gravado. A chave única no banco
    continua existindo como rede, para quem escreve por outro caminho."""
    urls = [f.url for f in obj.photos]
    if len(urls) != len(set(urls)):
        raise ValueError("a mesma foto aparece duas vezes na lista")
    return obj


class FotoImovel(Corpo):
    """Uma foto é uma REFERÊNCIA, não um arquivo.

    `https?` obrigatório e conferido também no banco: o que entra aqui vai para o `<img src>` da
    vitrine e para os dados estruturados da ficha, e um `javascript:` ou `data:` nesse lugar é
    script de terceiro rodando na página do cliente. A URL precisa ser pública e ESTÁVEL — link
    assinado que expira quebra o dado estruturado dias depois, quando ninguém está olhando.
    """
    url: str = Field(min_length=8, max_length=2000, pattern=r"^https?://")
    alt: str | None = Field(default=None, max_length=300)


class ImovelNovo(Corpo):
    code: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    city: str = Field(min_length=1, max_length=120)
    neighborhood: str = Field(min_length=1, max_length=120)
    type: str = Field(min_length=1, max_length=40)
    purpose: Literal["rent", "buy"]
    base_price_cents: Centavos
    condo_monthly_cents: Centavos | None = None
    property_tax_monthly_cents: Centavos | None = None
    other_monthly_cents: Centavos | None = None
    bedrooms: int = Field(ge=0, le=30)
    parking: int = Field(ge=0, le=30)
    area_m2: float | None = Field(default=None, gt=0, le=100_000)
    status: Literal["available", "reserved", "unavailable"] = "available"
    # A ordem da lista é a ordem na vitrine, e a primeira é a capa. Teto de 20 para um engano de
    # colagem não virar uma galeria infinita.
    photos: list[FotoImovel] = Field(default_factory=list, max_length=20)

    _sem_repetida = model_validator(mode="after")(lambda self: _conferir_fotos(self))


class FotosImovel(Corpo):
    photos: list[FotoImovel] = Field(default_factory=list, max_length=20)

    _sem_repetida = model_validator(mode="after")(lambda self: _conferir_fotos(self))


class SlotNovo(Corpo):
    property_id: str
    broker_id: str
    starts_at: datetime
    ends_at: datetime

    @model_validator(mode="after")
    def intervalo_positivo(self):
        if self.starts_at >= self.ends_at:
            raise ValueError("starts_at deve ser anterior a ends_at")
        return self


class VisitaNova(Corpo):
    opportunity_id: str
    property_id: str
    slot_id: str
    notes: str | None = Field(default=None, max_length=1000)


class TransicaoVisita(Corpo):
    target_status: Literal["confirmed", "completed", "cancelled", "no_show"]
    reason: str | None = Field(default=None, max_length=500)


class TarefaNova(Corpo):
    opportunity_id: str
    title: str = Field(min_length=1, max_length=200)
    kind: Literal["follow_up", "internal"]
    due_at: datetime | None = None
    assignee_id: str | None = None


class TarefaAlteracao(Corpo):
    status: Literal["open", "done", "cancelled"] | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    due_at: datetime | None = None
    assignee_id: str | None = None


class HandoffNovo(Corpo):
    opportunity_id: str
    reason: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=4000)
    # Para quem vai. Opcional: quem encaminha nem sempre sabe, e nesse caso a fila fica aberta para
    # qualquer corretor aceitar — que era o único comportamento possível antes deste campo existir.
    assignee_id: str | None = None


class TransicaoHandoff(Corpo):
    target_status: Literal["accepted", "resolved"]
    assignee_id: str | None = None
    # Resolver NÃO devolve o atendimento ao agente por padrão (seção 6): o corretor escolhe.
    # Campo obrigatório na resolução, e a rota recusa a omissão — silêncio aqui viraria uma
    # devolução automática que ninguém pediu.
    return_to: Literal["agent", "human"] | None = None
