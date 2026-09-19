"""RAG híbrido de imóveis sobre pgvector — ADR-0001.

Calibragem da busca por local: o cliente fala um lugar de qualquer jeito ("Pinheiros", "pinheiro",
"Vila Madalena", "perto da Faria Lima", "zona sul", "SP"). O `sdr_shared.geo` resolve isso para
bairro/região/cidade e a busca desce uma cascata — bairro → vizinhos → região → cidade — devolvendo
em `nivel` até onde precisou ir. O agente usa esse sinal para falar a verdade sobre o que encontrou,
em vez de deduzir indisponibilidade a partir de uma lista filtrada.
"""
from sdr_shared.config import get_settings
from sdr_shared.db import ImovelRepository
from sdr_shared.geo import Local, resolver, resolver_varios, vizinhos
from sdr_shared.models import CartaoQualificacao, ImovelCard, Intencao, Imovel


def _filtros(cartao: CartaoQualificacao, bairros: list[str] | None = None, regiao: str | None = "=") -> dict:
    return {"operacao": "aluguel" if cartao.intencao == Intencao.ALUGUEL else "venda",
            "regiao": cartao.regiao if regiao == "=" else regiao,
            "bairros": bairros or None,
            "preco_max": cartao.preco_max or cartao.ticket, "quartos": cartao.quartos}


def montar_card(i: Imovel, motivo: str | None = None) -> ImovelCard:
    # `motivo` vem da descrição do anúncio (cadastro do CRM ou do acervo): fonte externa que entra no prompt
    # do consultor. Neutralizamos aqui, na origem, para que um cadastro malicioso não injete instrução
    # (injeção de segunda ordem via RAG) em nenhum consumidor deste card.
    from ..util import neutralizar_texto_externo
    bruto = motivo if motivo is not None else (i.descricao or "")[:160]
    return ImovelCard(id=i.id, titulo=f"{i.tipo.capitalize()} {i.quartos}q · {i.bairro}", preco=i.preco,
                      foto=(i.fotos_absolutas(get_settings().public_api_url) or [None])[0],
                      motivo=neutralizar_texto_externo(bruto, limite=200))


def _consulta(cartao: CartaoQualificacao, preferencia: str, local: Local | None) -> str:
    partes = [preferencia, cartao.tipo_imovel, *(local.bairros if local else cartao.bairros)]
    if cartao.intencao == Intencao.INVESTIMENTO:
        partes.append("para renda de aluguel")
    return " ".join(filter(None, partes)).strip() or "imóvel"


def _executar(consulta: str, filtros: dict, limite: int) -> list[ImovelCard]:
    from sdr_shared.ports import get_embedder
    return [montar_card(i) for i in ImovelRepository().buscar_hibrido(get_embedder().embed(consulta), filtros, limite)]


def local_do_cartao(cartao: CartaoQualificacao) -> Local | None:
    """O local que o cliente pediu, resolvido. Preserva o TIPO: pedir "zona sul" é diferente de pedir
    "Moema" — no primeiro caso o agente não deve dizer que achou no bairro pedido."""
    locais = resolver_varios(cartao.bairros)
    if fora := next((l for l in locais if l.tipo == "fora"), None):
        return fora
    de_bairro = [l for l in locais if l.tipo == "bairro"]
    if de_bairro:
        bairros = list(dict.fromkeys(b for l in de_bairro for b in l.bairros))
        p = de_bairro[0]
        return Local(tipo="bairro", bairros=bairros, regiao=p.regiao, cidade=p.cidade,
                     termo=p.termo, via=p.via, confianca=p.confianca)
    if de_regiao := next((l for l in locais if l.tipo == "regiao"), None):
        return de_regiao
    if cidade := next((l for l in locais if l.tipo == "cidade"), None):
        return cidade
    if cartao.regiao:
        l = resolver(cartao.regiao)
        return l if l.tipo != "desconhecido" else None
    return None


def buscar_com_contexto(cartao: CartaoQualificacao, preferencia: str = "", limite: int = 5) -> dict:
    """Cascata bairro → vizinhos → região → cidade.

    Retorna {cards, nivel, local, bairros_pedidos, bairros_encontrados, ampliou, alternativa_no_bairro}.
    `nivel` diz onde a busca parou — é o que autoriza (ou não) o agente a falar de indisponibilidade.
    """
    local = local_do_cartao(cartao)
    consulta = _consulta(cartao, preferencia, local)
    pedidos = local.bairros if local and local.tipo == "bairro" else []
    # Cidade fora de cobertura: em vez de varrer a capital inteira, oferece a região mais próxima dela.
    if local and local.tipo == "fora":
        proxima = local.sugestao_regiao
        cards = _executar(consulta, _filtros(cartao, None, proxima), limite) if proxima else []
        if not cards:
            cards = _executar(consulta, _filtros(cartao, None, None), limite)
        return {"cards": cards, "nivel": "fora_de_cobertura", "local": local, "bairros_pedidos": [],
                "bairros_encontrados": sorted({c.titulo.split("·")[-1].strip() for c in cards}),
                "ampliou": True, "alternativa_no_bairro": []}

    def resposta(cards: list[ImovelCard], nivel: str, alternativa: list[ImovelCard] | None = None) -> dict:
        return {"cards": cards, "nivel": nivel, "local": local, "bairros_pedidos": pedidos,
                "bairros_encontrados": sorted({c.titulo.split("·")[-1].strip() for c in cards}),
                "ampliou": bool(pedidos) and nivel not in ("bairro", "vazio"),
                "alternativa_no_bairro": alternativa or []}

    # 1. o bairro que o cliente pediu
    if pedidos:
        if cards := _executar(consulta, _filtros(cartao, pedidos), limite):
            return resposta(cards, "bairro")
        # 2. vizinhos do bairro (mesma região, os mais próximos primeiro)
        proximos = [v for b in pedidos for v in vizinhos(b)]
        if proximos and (cards := _executar(consulta, _filtros(cartao, list(dict.fromkeys(proximos))), limite)):
            return resposta(cards, "vizinhos", _alternativa(cartao, pedidos, consulta))

    # 3. a região (a do local resolvido vence a do cartão, que o LLM pode ter errado)
    regiao = (local.regiao if local else None) or cartao.regiao
    if regiao and (cards := _executar(consulta, _filtros(cartao, None, regiao), limite)):
        return resposta(cards, "regiao", _alternativa(cartao, pedidos, consulta))

    # 4. a cidade inteira — melhor mostrar algo bom fora da área pedida do que dizer "não temos nada"
    if cards := _executar(consulta, _filtros(cartao, None, None), limite):
        return resposta(cards, "cidade", _alternativa(cartao, pedidos, consulta))

    return resposta([], "vazio", _alternativa(cartao, pedidos, consulta))


def _alternativa(cartao: CartaoQualificacao, pedidos: list[str], consulta: str) -> list[ImovelCard]:
    """O que EXISTE no bairro pedido fora do perfil exato (relaxa quartos e, depois, preço).
    É o que um bom corretor diz: 'de 2 quartos não tenho aí, mas tenho este de 1'."""
    if not pedidos:
        return []
    if cartao.quartos and (r := _executar(consulta, _filtros(cartao.model_copy(update={"quartos": None}), pedidos), 3)):
        return r
    if cartao.preco_max and (r := _executar(consulta, _filtros(cartao.model_copy(update={"preco_max": None, "ticket": None}), pedidos), 3)):
        return r
    return []


def buscar_imoveis(cartao: CartaoQualificacao, preferencia: str = "", limite: int = 5) -> list[ImovelCard]:
    return buscar_com_contexto(cartao, preferencia, limite)["cards"]
