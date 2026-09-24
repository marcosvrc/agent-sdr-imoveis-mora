"""Conversa humanizada que preenche o CartaoQualificacao. Extração estruturada (Haiku) + resposta (Sonnet)."""
import re

from pydantic import Field

from sdr_shared.db import ClienteRepository, auditar, nova_oportunidade_se_mudou_intencao
from sdr_shared.messaging import RespostaAgente
from sdr_shared.models import CartaoQualificacao, Estagio, Intencao, Segmento
from ..llm import llm_conversa, llm_roteamento
from ..prompts import carregar, texto
from ..state import AgentState
from ..guardrails.saida import sanear
from sdr_shared.geo import resolver, resolver_varios


def ultima_pergunta(messages) -> str:
    """A última fala da Mora — o que dá sentido a uma resposta curta.

    Sem ela, "1" logo depois de "quantos quartos?" não informa nada explicitamente, e a extração
    (que é conservadora de propósito: não inferir é o que a impede de alucinar orçamento) devolve
    nulo com toda a razão. O cartão nunca fecha, o consultor nunca roda, e o cliente fica olhando
    para uma promessa de busca que não vem. Foi exatamente o que aconteceu no primeiro teste com
    gente de verdade digitando.
    """
    for m in reversed(list(messages or [])):
        papel = getattr(m, "type", None) or (m[0] if isinstance(m, (tuple, list)) and m else None)
        if papel in ("ai", "assistant"):
            conteudo = getattr(m, "content", None)
            if conteudo is None and isinstance(m, (tuple, list)) and len(m) > 1:
                conteudo = m[1]
            return str(conteudo or "")[-300:]
    return ""


class Extracao(CartaoQualificacao):
    """O que a extração devolve: o cartão, mais o canal de RETIRADA.

    Sem `limpar` o merge só sabe escrever valor sobre valor, e um critério que o cliente desfaz
    ("tanto faz o bairro agora", "não tenho mais teto") fica no cartão para sempre, guiando toda
    busca seguinte. Retirar é um ato explícito do cliente e por isso é um campo, não a ausência de
    um: ausência continua significando "não falou disso", que é o caso comum e não pode apagar nada.
    """
    limpar: list[str] = Field(default_factory=list)


# "Não preencheu". Zero e False ficam de fora desta lista de propósito: `quartos = 0` é studio ou
# kitnet, e descartá-lo fazia a Mora perguntar de novo quantos quartos alguém quer num quarto só.
_NAO_INFORMADO = (None, [], Intencao.INDEFINIDA, Segmento.INDEFINIDO)
# Onde zero não é resposta: preço zero, área zero e ticket zero são erro de extração, não pedido.
_ZERO_NAO_VALE = frozenset({"preco_min", "preco_max", "ticket", "area_min"})
# O que o cliente pode desfazer. `intencao` e `segmento` não entram: sem intenção não há rota, e
# zerá-las no meio da conversa devolveria o lead ao começo. Contato também não — quem deu o
# telefone não o retira por engano de extração; isso é assunto de privacidade, não de busca.
_LIMPAVEIS = frozenset({"regiao", "bairros", "preco_min", "preco_max", "quartos", "area_min",
                        "tipo_imovel", "urgencia", "requisitos", "pediu_visita",
                        "perfil_investidor", "ticket", "retorno_esperado"})


def _vale(campo: str, valor) -> bool:
    """O modelo disse alguma coisa sobre este campo?"""
    if isinstance(valor, str) and not valor.strip():
        return False
    if valor is False:                                  # "não pediu visita" é o default, não um fato
        return False
    if valor in _NAO_INFORMADO:
        return False
    return not (valor == 0 and campo in _ZERO_NAO_VALE)


def _extrair(cartao: CartaoQualificacao, mensagem: str, pergunta: str = "") -> CartaoQualificacao:
    try:
        novo = llm_roteamento().with_structured_output(Extracao).invoke(
            texto("extracao", cartao=cartao.model_dump(exclude_defaults=True), mensagem=mensagem,
                  pergunta=pergunta.strip() or "(nenhuma — é a primeira mensagem da conversa)"))
    except Exception:
        return cartao
    if not isinstance(novo, CartaoQualificacao):        # saída estruturada pode vir como dict cru
        return cartao
    dados = {k: v for k, v in novo.model_dump(exclude={"limpar"}).items() if _vale(k, v)}
    dados["imoveis_visualizados"] = list(dict.fromkeys(cartao.imoveis_visualizados + novo.imoveis_visualizados))
    for campo in (getattr(novo, "limpar", None) or []):
        campo = str(campo).strip().lower()
        if campo in _LIMPAVEIS:                         # o que veio fora da lista é ignorado em silêncio
            dados[campo] = CartaoQualificacao.model_fields[campo].get_default(call_default_factory=True)
    return cartao.model_copy(update=dados)


def _absorver_contato(lead) -> None:
    """O que o cliente informou na conversa vira dado do lead — é o que o corretor usa para ligar."""
    c = lead.cartao
    capturado = []
    if c.nome_informado and not lead.nome:
        lead.nome = c.nome_informado.strip()[:80]
        capturado.append("nome")
    if c.telefone_informado and not lead.telefone:
        so_digitos = re.sub(r"\D", "", c.telefone_informado)
        if 10 <= len(so_digitos) <= 13:                       # DDD + número; evita gravar lixo
            lead.telefone = so_digitos
            capturado.append("telefone")
    if c.email_informado and not lead.email:
        lead.email = c.email_informado.strip().lower()[:120]
        capturado.append("email")
    if capturado:
        # registra QUE o contato foi capturado; o valor em si fica no cadastro do lead, não na trilha
        auditar(acao="lead.contato_capturado", entidade="lead", entidade_id=lead.id, ator_tipo="agente",
                ator_nome="Mora", dados={"campos": capturado})
    if ("telefone" in capturado or "email" in capturado) and not lead.cliente_id:
        # com um contato na mão dá para dizer que esta conversa e a do Telegram são a mesma pessoa
        anterior = ClienteRepository().por_contato(lead.telefone, lead.email)
        if ClienteRepository().vincular(lead) and anterior:
            auditar(acao="cliente.reconhecido", entidade="cliente", entidade_id=lead.cliente_id,
                    ator_tipo="agente", ator_nome="Mora",
                    dados={"lead_id": lead.id, "por": "telefone" if "telefone" in capturado else "email"})


def _normalizar_local(cartao: CartaoQualificacao, mensagem: str) -> tuple[CartaoQualificacao, str | None]:
    """O LLM extrai o local como o cliente falou; QUEM decide bairro/região é o catálogo (sdr_shared.geo).
    Devolve o cartão ajustado e, quando o cliente cita lugar fora da cobertura, o nome dele."""
    locais = resolver_varios(cartao.bairros)
    if not locais and not cartao.regiao and mensagem:
        l = resolver(mensagem)                                   # varre a frase: "quero perto da Faria Lima"
        locais = [l] if l.tipo != "desconhecido" else []
    fora = next((l for l in locais if l.tipo == "fora"), None)
    if fora:
        return cartao.model_copy(update={"bairros": [], "regiao": None}), fora.cidade or fora.termo
    bairros = list(dict.fromkeys(b for l in locais if l.tipo == "bairro" for b in l.bairros))
    regiao = next((l.regiao for l in locais if l.regiao), None) or cartao.regiao
    if regiao and regiao not in ("zona_sul", "zona_oeste", "zona_norte", "zona_leste", "centro"):
        regiao = (resolver(regiao).regiao)                        # o LLM pode ter escrito "Pinheiros" em regiao
    return cartao.model_copy(update={"bairros": bairros or cartao.bairros, "regiao": regiao}), None


def _contexto_contato(lead, state) -> str:
    """Pedir contato cedo demais derruba a conversa; tarde demais perde o lead. A regra está aqui."""
    from sdr_shared.messaging import Canal
    if state["entrada"].canal != Canal.WEB:
        return ""                                   # no Telegram já temos identificador e nome do perfil
    if not lead.nome:
        return ("Se ainda não souber o nome do cliente, pergunte-o de forma leve numa das próximas mensagens "
                "(ex.: 'como posso te chamar?') — apenas o primeiro nome, nunca junto com outros dados.")
    if not lead.cartao.tem_contato() and lead.cartao.completo():
        return ("O cliente já disse o que procura. Ao apresentar as opções ou marcar algo, peça UM contato "
                "(telefone de preferência) explicando para quê: 'me passa seu telefone que te mando as fotos "
                "e o corretor confirma a visita'. Não insista se ele não quiser, e não peça e-mail junto.")
    return ""


def run(state: AgentState) -> dict:
    lead, entrada = state["lead"], state["entrada"]
    fora_de_cobertura = None
    if entrada.conteudo:
        pergunta = ultima_pergunta(state.get("messages"))
        novo_cartao = _extrair(lead.cartao, entrada.conteudo, pergunta)
        # quem já fechou um ciclo e volta com outra intenção começa uma oportunidade nova, não sobrescreve a antiga
        if (sucessora := nova_oportunidade_se_mudou_intencao(lead, novo_cartao.intencao)):
            auditar(acao="oportunidade.aberta", entidade="lead", entidade_id=sucessora.id, ator_tipo="agente",
                    ator_nome="Mora", dados={"anterior": lead.id, "cliente_id": lead.cliente_id,
                                              "de": str(lead.cartao.intencao), "para": str(novo_cartao.intencao)})
            # o cartão da nova oportunidade sai SÓ desta mensagem: o que ela procura agora é outra coisa,
            # mas o contato e o nome seguem sendo da mesma pessoa
            contato = {c: getattr(lead.cartao, c) for c in ("nome_informado", "telefone_informado", "email_informado")}
            sucessora.cartao = _extrair(CartaoQualificacao(), entrada.conteudo, pergunta).model_copy(
                update={**contato, "intencao": novo_cartao.intencao})
            lead = sucessora
        else:
            lead.cartao = novo_cartao
        lead.cartao, fora_de_cobertura = _normalizar_local(lead.cartao, entrada.conteudo)
    _absorver_contato(lead)
    if lead.estagio == Estagio.NOVO and lead.cartao.intencao != Intencao.INDEFINIDA:
        lead.estagio = Estagio.QUALIFICANDO

    # Cartão ficou completo com esta mensagem: não prometer "vou buscar" — o consultor responde já com os imóveis.
    # (O supervisor decidiu antes da extração; sem isto o modelo inventa uma "ferramenta" em texto.)
    if lead.cartao.completo() and not state.get("imoveis_sugeridos"):
        # `cartao_extraido_de`: o consultor recebe o turno agora e leria esta mesma frase de novo.
        return {"lead": lead, "proximo": "consultor", "cartao_extraido_de": entrada.conteudo}

    origem = ""
    if lead.cartao.imoveis_visualizados:
        origem = (f"O cliente demonstrou interesse nos imóveis {lead.cartao.imoveis_visualizados} (viu no site). "
                  "Use isso como ponto de partida e não pergunte o que dá para inferir deles.")
    cobertura = ""
    if fora_de_cobertura:
        cobertura = (f"ATENÇÃO: o cliente citou {fora_de_cobertura}, que está FORA da área de cobertura. Diga isso com "
                     "transparência em uma frase, ofereça as regiões atendidas (sugira a mais próxima) e pergunte se "
                     "alguma serve. Não prometa buscar nesse lugar.")
    # Só a primeira mensagem da conversa se apresenta; da segunda em diante repetir o nome do
    # assistente é justamente o que faz um bot soar como bot.
    abertura = ("Esta é a PRIMEIRA mensagem desta conversa: apresente-se em meia frase (Mora, da "
                "Vértice Imóveis) antes de perguntar."
                if state.get("primeira_interacao") else
                "A conversa já está em andamento: não se apresente de novo nem repita boas-vindas.")
    prompt = carregar("qualificador", memoria=lead.resumo, nome=lead.nome or "cliente", intencao=lead.cartao.intencao,
                      faltantes=lead.cartao.campos_faltantes() or ["nenhum"], contexto_origem=origem,
                      contexto_cobertura=cobertura, contexto_abertura=abertura,
                      contexto_contato=_contexto_contato(lead, state))
    msg = llm_conversa().invoke([prompt, *state["messages"]])

    opcoes = ["Comprar", "Alugar", "Investir"] if lead.cartao.intencao == Intencao.INDEFINIDA else []
    return {"lead": lead, "messages": [msg],
            "resposta": RespostaAgente(lead_id=lead.id, texto=sanear(msg.content, lead.id), opcoes=opcoes)}
