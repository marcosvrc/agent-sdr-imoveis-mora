"""Regras do funil (seção 6 da especificação).

Tudo aqui é função pura sobre dados já lidos do banco. A razão é prática: estas são as regras que
mais mudam e as que mais precisam de teste, e testá-las sem transação, sem HTTP e sem Postgres é o
que torna viável cobrir os casos de canto — que são a maioria.
"""
from dataclasses import dataclass

ESTAGIOS = ("new", "in_service", "qualified", "visit_scheduled", "negotiation", "won", "lost")

# Origem -> destinos permitidos. Tabela, e não uma cadeia de `if`, porque ela é a transcrição
# literal da seção 6: dá para conferir linha a linha contra o documento.
PERMITIDAS: dict[str, frozenset[str]] = {
    "new": frozenset({"in_service", "lost"}),
    "in_service": frozenset({"qualified", "lost"}),
    "qualified": frozenset({"visit_scheduled", "negotiation", "lost"}),
    "visit_scheduled": frozenset({"qualified", "negotiation", "lost"}),
    "negotiation": frozenset({"won", "lost"}),
    "won": frozenset({"in_service"}),          # reabertura administrativa
    "lost": frozenset({"in_service"}),
}

# Transições que o agente NUNCA faz, mesmo tendo o scope. A separação entre "pode pela credencial"
# e "pode pelo papel" é explícita na seção 4: scope não é autorização.
SOMENTE_HUMANO: frozenset[tuple[str, str]] = frozenset({
    ("qualified", "negotiation"),
    ("visit_scheduled", "negotiation"),
    ("negotiation", "won"),
    ("negotiation", "lost"),
    ("new", "lost"), ("in_service", "lost"), ("qualified", "lost"), ("visit_scheduled", "lost"),
    ("won", "in_service"), ("lost", "in_service"),
})

# Motivo é exigido pela TRANSIÇÃO, não pelo estágio de destino. `in_service` aparece duas vezes na
# tabela com significados opostos: vindo de `new` é o atendimento começando (não há motivo a dar),
# e vindo de `won`/`lost` é uma reabertura administrativa (que precisa dizer por quê). Amarrar a
# exigência ao destino obrigaria a inventar um motivo para toda primeira mensagem de todo lead.
EXIGEM_MOTIVO: frozenset[tuple[str, str]] = frozenset(
    [(origem, "lost") for origem in ("new", "in_service", "qualified", "visit_scheduled", "negotiation")]
    + [("won", "in_service"), ("lost", "in_service")])

# Campos sem os quais "qualificado" é uma afirmação vazia: sem cidade, propósito e teto de
# orçamento não há como buscar um imóvel para a pessoa.
CAMPOS_DE_QUALIFICACAO = ("city", "purpose", "budget_max_cents")


@dataclass(frozen=True)
class Contexto:
    """O que a decisão precisa saber sobre a oportunidade, já carregado."""

    stage: str
    purpose: str
    atendimento: str
    preferencias: dict
    tem_visita_confirmada_futura: bool = False


def campos_faltantes(ctx: Contexto) -> list[str]:
    p = dict(ctx.preferencias or {})
    p.setdefault("purpose", ctx.purpose)
    return [c for c in CAMPOS_DE_QUALIFICACAO if p.get(c) in (None, "", [])]


@dataclass(frozen=True)
class Veredito:
    ok: bool
    code: str = ""
    mensagem: str = ""
    detalhes: dict | None = None


def avaliar(ctx: Contexto, destino: str, *, humano: bool, motivo: str | None) -> Veredito:
    """Responde se a transição pode acontecer — e, quando não pode, por quê e o que falta.

    A ordem das checagens é intencional. Primeiro o que é estrutural (destino existe, transição
    existe no mapa), depois quem está no comando, depois permissão de papel, e só então a regra de
    negócio que exige ir buscar dado. Assim o agente que tentar `won` recebe 403 — e não uma lista
    de campos faltantes que o levaria a insistir numa ação que ele nunca poderá fazer.
    """
    if destino not in ESTAGIOS:
        return Veredito(False, "INVALID_TRANSITION", f"Estágio '{destino}' não existe.")
    if destino == ctx.stage:
        return Veredito(False, "INVALID_TRANSITION", f"A oportunidade já está em '{destino}'.")
    if destino not in PERMITIDAS.get(ctx.stage, frozenset()):
        return Veredito(False, "INVALID_TRANSITION",
                        f"De '{ctx.stage}' não se vai para '{destino}'.",
                        {"allowed": sorted(PERMITIDAS.get(ctx.stage, frozenset()))})

    # Encaminhamento aberto ou aceito congela a mão do agente — mas não a do corretor, que é
    # justamente quem foi chamado para resolver.
    if not humano and ctx.atendimento in {"human_pending", "human"}:
        return Veredito(False, "HUMAN_IN_CONTROL",
                        "O atendimento está com um corretor; o agente não movimenta a oportunidade.")

    if not humano and (ctx.stage, destino) in SOMENTE_HUMANO:
        return Veredito(False, "FORBIDDEN", f"'{ctx.stage}' → '{destino}' é ação humana.")

    if (ctx.stage, destino) in EXIGEM_MOTIVO and not (motivo or "").strip():
        return Veredito(False, "REASON_REQUIRED", f"'{ctx.stage}' → '{destino}' exige motivo.")

    if destino == "qualified" and ctx.stage == "in_service":
        faltam = campos_faltantes(ctx)
        if faltam:
            return Veredito(False, "QUALIFICATION_INCOMPLETE",
                            "Faltam dados para qualificar.", {"missing_fields": faltam})

    # `visit_scheduled` é consequência de uma visita confirmada, não um estado que se declara. Sem
    # esta checagem o estágio viraria uma opinião: o funil diria "visita marcada" sem visita.
    if destino == "visit_scheduled" and not ctx.tem_visita_confirmada_futura:
        return Veredito(False, "VISIT_NOT_CONFIRMED",
                        "Só vai para 'visit_scheduled' com uma visita confirmada no futuro.")

    return Veredito(True)


def estagio_apos_cancelar_visita(ctx: Contexto) -> str | None:
    """Recalcula o estágio quando a última visita futura confirmada é cancelada (seção 6).

    Devolve `None` quando nada muda. Negociação não regride: quem já está negociando não volta a
    ser um lead qualificado porque uma visita caiu — a conversa avançou para além dela.
    """
    if ctx.stage == "visit_scheduled" and not ctx.tem_visita_confirmada_futura:
        return "qualified"
    return None
