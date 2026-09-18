"""Custo de um imóvel (seção 6).

A regra inteira cabe em uma frase, e é a frase mais importante deste arquivo: **campo desconhecido
é `None`, nunca zero**. Um condomínio não informado tratado como zero produz um total menor que o
real — e o cliente descobre a diferença no dia da assinatura, o que é exatamente o tipo de surpresa
que um SDR não pode causar.
"""
from dataclasses import dataclass

MENSAIS = ("condo_monthly_cents", "property_tax_monthly_cents", "other_monthly_cents")


@dataclass(frozen=True)
class Custo:
    base_price_cents: int
    monthly_total_cents: int | None       # None quando algum componente é desconhecido
    componentes: dict[str, int | None]
    incompleto: bool
    faltando: tuple[str, ...]

    def para_json(self) -> dict:
        return {"base_price_cents": self.base_price_cents,
                "monthly_total_cents": self.monthly_total_cents,
                "monthly_components": self.componentes,
                "monthly_total_incomplete": self.incompleto,
                "monthly_missing": list(self.faltando)}


def calcular(imovel: dict) -> Custo:
    """Aluguel: total mensal = aluguel + condomínio + IPTU mensal + outros.

    Compra não tem total mensal — e a especificação proíbe somar o preço de compra aos custos
    mensais. São grandezas diferentes; somá-las produziria um número sem significado nenhum.
    """
    base = int(imovel["base_price_cents"])
    componentes: dict[str, int | None] = {c: imovel.get(c) for c in MENSAIS}

    if imovel["purpose"] != "rent":
        return Custo(base, None, componentes, False, ())

    componentes = {"base_price_cents": base, **componentes}
    faltando = tuple(c for c in MENSAIS if imovel.get(c) is None)
    if faltando:
        return Custo(base, None, componentes, True, faltando)
    return Custo(base, base + sum(int(imovel[c]) for c in MENSAIS), componentes, False, ())


def cabe_no_orcamento(imovel: dict, teto_cents: int | None, base: str) -> bool | None:
    """Compara com o teto na base pedida. Devolve `None` quando o total é desconhecido.

    `None` não é "não cabe": é "não dá para afirmar". Quem chama decide se mostra o imóvel marcado
    como incompleto (o que a especificação pede no painel) ou se o exclui — mas a decisão fica à
    vista, em vez de virar um filtro silencioso que esconde imóveis por falta de cadastro.
    """
    if teto_cents is None:
        return True
    custo = calcular(imovel)
    if base == "monthly_total" and imovel["purpose"] == "rent":
        if custo.monthly_total_cents is None:
            return None
        return custo.monthly_total_cents <= teto_cents
    return custo.base_price_cents <= teto_cents
