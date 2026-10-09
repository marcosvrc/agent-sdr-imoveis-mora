"""RAG híbrido de imóveis sobre pgvector — ADR-0001.

Calibragem da busca por local: o cliente fala um lugar de qualquer jeito ("Pinheiros", "pinheiro",
"Vila Madalena", "perto da Faria Lima", "zona sul", "SP"). O `sdr_shared.geo` resolve isso para
bairro/região/cidade e a busca desce uma cascata — bairro → vizinhos → região → cidade — devolvendo
em `nivel` até onde precisou ir. O agente usa esse sinal para falar a verdade sobre o que encontrou,
em vez de deduzir indisponibilidade a partir de uma lista filtrada.
"""
import logging

from sdr_shared.config import get_settings
from sdr_shared.db import ImovelRepository
from sdr_shared.geo import BAIRROS, Local, resolver, resolver_varios, vizinhos
from sdr_shared.models import (CartaoQualificacao, ImovelCard, Imovel, Intencao, Segmento,
                               TIPOS_COMERCIAIS, TIPOS_RESIDENCIAIS)


log = logging.getLogger("agent.busca")


def _filtros(cartao: CartaoQualificacao, bairros: list[str] | None = None, regiao: str | None = "=") -> dict:
    """O segmento decide QUAL filtro de tamanho vale.

    Comercial não é residencial sem quartos: quem procura sala decide por metro quadrado, e o
    `quartos` do cartão (que nesse caso não existe) não pode virar `quartos >= None` em silêncio
    nem, pior, restar de uma conversa anterior e esconder o acervo comercial inteiro.

    Bairro pedido dispensa a região: o bairro já é o recorte mais fino, e somar os dois filtros
    descartava em silêncio todo bairro que não fosse da região do PRIMEIRO. Um lead pediu "Tatuapé
    ou Tucuruvi"; o cartão guardou `zona_leste` (a do Tatuapé), o SQL virou `bairro IN (Tatuapé,
    Tucuruvi) AND regiao = 'zona_leste'`, e quatro imóveis do Tucuruvi (zona norte) sumiram — com a
    Mora dizendo "achei duas opções" como se fosse tudo.
    """
    comercial = cartao.segmento_efetivo() == Segmento.COMERCIAL
    if bairros:
        regiao = None
    return {"operacao": "aluguel" if cartao.intencao == Intencao.ALUGUEL else "venda",
            "regiao": cartao.regiao if regiao == "=" else regiao,
            "bairros": bairros or None,
            "preco_max": cartao.preco_max or cartao.ticket,
            "quartos": None if comercial else cartao.quartos,
            "area_min": cartao.area_min if comercial else None,
            "tipos": list(TIPOS_COMERCIAIS if comercial else TIPOS_RESIDENCIAIS)}


def _medida(i: Imovel) -> str:
    """Como o imóvel se mede na frase do corretor: apartamento por quartos, sala por metro."""
    from sdr_shared.models import segmento_do_tipo
    if segmento_do_tipo(i.tipo) == Segmento.COMERCIAL or not i.quartos:
        return f"{i.area_m2:.0f} m²"
    return f"{i.quartos}q"


def montar_card(i: Imovel, motivo: str | None = None) -> ImovelCard:
    # `motivo` vem da descrição do anúncio (cadastro do CRM ou do acervo): fonte externa que entra no prompt
    # do consultor. Neutralizamos aqui, na origem, para que um cadastro malicioso não injete instrução
    # (injeção de segunda ordem via RAG) em nenhum consumidor deste card.
    from ..util import neutralizar_texto_externo
    bruto = motivo if motivo is not None else (i.descricao or "")[:160]
    return ImovelCard(id=i.id, titulo=f"{i.tipo.capitalize()} {_medida(i)} · {i.bairro}", preco=i.preco,
                      foto=(i.fotos_absolutas(get_settings().public_api_url) or [None])[0],
                      motivo=neutralizar_texto_externo(bruto, limite=200))


def _consulta(cartao: CartaoQualificacao, preferencia: str, local: Local | None) -> str:
    """O texto que vira vetor. `preferencia` é a fala deste turno; os requisitos são o que o cliente
    pediu em QUALQUER turno — sem eles, "aceita pet" influenciava o ranking uma vez e nunca mais."""
    partes = [preferencia, cartao.tipo_imovel, *(local.bairros if local else cartao.bairros),
              *cartao.requisitos]
    if cartao.intencao == Intencao.INVESTIMENTO:
        partes.append("para renda de aluguel")
    return " ".join(filter(None, partes)).strip() or "imóvel"


def _vetor(consulta: str) -> list[float] | None:
    """Um embedding por busca. A cascata abaixo chama `_executar` até seis vezes com a MESMA
    consulta (bairro, vizinhos, região, cidade, mais as alternativas) — e cada chamada ia ao
    Ollama de novo pelo mesmo vetor: seis viagens de ~100 ms para calcular seis vezes o mesmo número.

    `None` quando não há embedder (Ollama fora do ar, provedor sem chave): a busca segue só com os
    filtros SQL. Antes, a exceção subia até o consultor e o turno inteiro caía no fallback de
    handoff — o cliente era mandado ao corretor porque um serviço auxiliar tossiu."""
    from sdr_shared.ports import get_embedder
    try:
        return get_embedder().embed(consulta)
    except Exception:
        log.warning("sem embedding para a busca; seguindo só com filtros", exc_info=True)
        return None


def ficha(i: Imovel) -> str:
    """Os fatos do imóvel, para o modelo ter o que dizer sem inventar.

    O prompt do consultor recebia título, preço e um pedaço do anúncio — e a ordem de citar "um
    diferencial de cada". Metragem, suítes, vagas e condomínio existem no banco desde sempre e não
    chegavam nele; o modelo então argumentava com o que dava, que é a definição do problema.

    Condomínio em branco é DESCONHECIDO, nunca zero: zero significa que o imóvel não tem condomínio,
    e a diferença entre as duas coisas é dinheiro no bolso de quem aluga.
    """
    partes = [f"{i.area_m2:.0f} m²" if i.area_m2 else None]
    if i.quartos:
        partes.append(f"{i.quartos} quarto(s)" + (f", {i.suites} suíte(s)" if i.suites else ""))
    if i.vagas:
        partes.append(f"{i.vagas} vaga(s)")
    if i.condominio is None:
        partes.append("condomínio não informado")
    elif i.condominio:
        partes.append(f"condomínio R$ {i.condominio:,.0f}".replace(",", "."))
    else:
        partes.append("sem condomínio")
    return " · ".join(p for p in partes if p)


def _executar(vetor: list[float] | None, filtros: dict, limite: int,
              cartao: CartaoQualificacao | None = None, fichas: dict | None = None) -> list[ImovelCard]:
    repo = ImovelRepository()
    imoveis = (repo.buscar_por_filtros(filtros, limite) if vetor is None
               else repo.buscar_hibrido(vetor, filtros, limite))
    if fichas is not None and cartao is not None:
        from sdr_shared.reativacao import pontuar_cartao
        for i in imoveis:
            # O mesmo gerador de motivo verificável da reativação (ADR-0013), aqui para o consultor
            # ter POR QUE este imóvel, e não o texto do anunciante.
            fichas[i.id] = {"ficha": ficha(i), "motivos": pontuar_cartao(cartao, i)[1]}
    return [montar_card(i) for i in imoveis]


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


def _intercalar(listas: list[list[ImovelCard]], limite: int) -> list[ImovelCard]:
    """Um de cada lista por vez, sem repetir: com dois bairros pedidos, os três primeiros cards não
    podem sair todos do mesmo só porque o ranking semântico favoreceu um deles."""
    vistos, saida = set(), []
    for rodada in range(max((len(l) for l in listas), default=0)):
        for lista in listas:
            if rodada < len(lista) and lista[rodada].id not in vistos:
                vistos.add(lista[rodada].id)
                saida.append(lista[rodada])
    return saida[:limite]


def _regioes_dos_bairros(bairros: list[str]) -> list[str]:
    """As regiões de TODOS os bairros pedidos, na ordem em que foram citados."""
    return list(dict.fromkeys(BAIRROS[b]["regiao"] for b in bairros if b in BAIRROS))


def _por_bairro(vetor, cartao: CartaoQualificacao, bairros: list[str], limite: int,
                fichas: dict) -> dict[str, list[ImovelCard]]:
    """Uma busca por bairro. Uma só, com `bairro IN (...)`, deixava o ranking decidir a proporção —
    e quem pediu dois lugares quer ver os dois."""
    if len(bairros) == 1:
        return {bairros[0]: _executar(vetor, _filtros(cartao, bairros), limite, cartao, fichas)}
    return {b: _executar(vetor, _filtros(cartao, [b]), limite, cartao, fichas) for b in bairros}


def buscar_com_contexto(cartao: CartaoQualificacao, preferencia: str = "", limite: int = 5) -> dict:
    """Cascata bairro → vizinhos → região → cidade.

    Retorna {cards, nivel, local, bairros_pedidos, bairros_encontrados, bairros_sem_resultado,
    ampliou, alternativa_no_bairro}. `nivel` diz onde a busca parou — é o que autoriza (ou não) o
    agente a falar de indisponibilidade. Com mais de um bairro pedido, cada um é buscado à parte e os
    cards se intercalam; `bairros_sem_resultado` lista os pedidos que ficaram vazios, para o agente
    dizer isso em vez de apresentar o que achou como se fosse tudo.
    """
    local = local_do_cartao(cartao)
    fichas: dict[str, dict] = {}
    vetor = _vetor(_consulta(cartao, preferencia, local))
    pedidos = local.bairros if local and local.tipo == "bairro" else []
    # Cidade fora de cobertura: em vez de varrer a capital inteira, oferece a região mais próxima dela.
    if local and local.tipo == "fora":
        proxima = local.sugestao_regiao
        cards = _executar(vetor, _filtros(cartao, None, proxima), limite, cartao, fichas) if proxima else []
        if not cards:
            cards = _executar(vetor, _filtros(cartao, None, None), limite, cartao, fichas)
        return {"cards": cards, "nivel": "fora_de_cobertura", "local": local, "bairros_pedidos": [], "fichas": fichas,
                "bairros_encontrados": sorted({c.titulo.split("·")[-1].strip() for c in cards}),
                "bairros_sem_resultado": [], "ampliou": True, "alternativa_no_bairro": []}

    def resposta(cards: list[ImovelCard], nivel: str, alternativa: list[ImovelCard] | None = None,
                 sem_resultado: list[str] | None = None) -> dict:
        return {"cards": cards, "nivel": nivel, "local": local, "bairros_pedidos": pedidos, "sem_embedding": vetor is None, "fichas": fichas,
                "bairros_encontrados": sorted({c.titulo.split("·")[-1].strip() for c in cards}),
                "bairros_sem_resultado": sem_resultado or [],
                "ampliou": bool(pedidos) and nivel not in ("bairro", "vazio"),
                "alternativa_no_bairro": alternativa or []}

    # 1. o(s) bairro(s) que o cliente pediu — cada um à parte, intercalados
    if pedidos:
        achados = _por_bairro(vetor, cartao, pedidos, limite, fichas)
        if cards := _intercalar(list(achados.values()), limite):
            return resposta(cards, "bairro", sem_resultado=[b for b, l in achados.items() if not l])
        # 2. vizinhos do bairro (mesma região, os mais próximos primeiro)
        proximos = [v for b in pedidos for v in vizinhos(b)]
        if proximos and (cards := _executar(vetor, _filtros(cartao, list(dict.fromkeys(proximos))), limite, cartao, fichas)):
            return resposta(cards, "vizinhos", _alternativa(cartao, pedidos, vetor, fichas))

    # 3. a região — de CADA bairro pedido; sem bairro, a do local resolvido vence a do cartão,
    #    que o LLM pode ter errado
    regioes = _regioes_dos_bairros(pedidos) or [r for r in [(local.regiao if local else None) or cartao.regiao] if r]
    if regioes and (cards := _intercalar([_executar(vetor, _filtros(cartao, None, r), limite, cartao, fichas)
                                          for r in regioes], limite)):
        return resposta(cards, "regiao", _alternativa(cartao, pedidos, vetor, fichas))

    # 4. a cidade inteira — melhor mostrar algo bom fora da área pedida do que dizer "não temos nada"
    if cards := _executar(vetor, _filtros(cartao, None, None), limite, cartao, fichas):
        return resposta(cards, "cidade", _alternativa(cartao, pedidos, vetor, fichas))

    return resposta([], "vazio", _alternativa(cartao, pedidos, vetor, fichas))


def _alternativa(cartao: CartaoQualificacao, pedidos: list[str], vetor: list[float],
                 fichas: dict | None = None) -> list[ImovelCard]:
    """O que EXISTE no bairro pedido fora do perfil exato (relaxa quartos e, depois, preço).
    É o que um bom corretor diz: 'de 2 quartos não tenho aí, mas tenho este de 1'."""
    if not pedidos:
        return []
    comercial = cartao.segmento_efetivo() == Segmento.COMERCIAL
    afrouxar = {"area_min": None} if comercial else {"quartos": None}
    if (cartao.area_min if comercial else cartao.quartos) and \
            (r := _executar(vetor, _filtros(cartao.model_copy(update=afrouxar), pedidos), 3, cartao, fichas)):
        return r
    if cartao.preco_max and (r := _executar(vetor, _filtros(cartao.model_copy(update={"preco_max": None, "ticket": None}), pedidos), 3, cartao, fichas)):
        return r
    return []


def buscar_imoveis(cartao: CartaoQualificacao, preferencia: str = "", limite: int = 5) -> list[ImovelCard]:
    return buscar_com_contexto(cartao, preferencia, limite)["cards"]
