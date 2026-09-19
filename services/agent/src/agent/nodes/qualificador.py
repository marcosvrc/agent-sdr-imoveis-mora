"""Conversa humanizada que preenche o CartaoQualificacao. Extração estruturada (Haiku) + resposta (Sonnet)."""
import re

from sdr_shared.db import ClienteRepository, auditar, nova_oportunidade_se_mudou_intencao
from sdr_shared.messaging import RespostaAgente
from sdr_shared.models import CartaoQualificacao, Estagio, Intencao
from ..llm import llm_conversa, llm_roteamento
from ..prompts import carregar, texto
from ..state import AgentState
from ..guardrails.saida import sanear
from sdr_shared.geo import resolver, resolver_varios


def _extrair(cartao: CartaoQualificacao, mensagem: str) -> CartaoQualificacao:
    try:
        novo = llm_roteamento().with_structured_output(CartaoQualificacao).invoke(
            texto("extracao", cartao=cartao.model_dump(exclude_defaults=True), mensagem=mensagem))
    except Exception:
        return cartao
    dados = {k: v for k, v in novo.model_dump().items()
             if v not in (None, [], False, Intencao.INDEFINIDA, 0)}
    dados["imoveis_visualizados"] = list(dict.fromkeys(cartao.imoveis_visualizados + novo.imoveis_visualizados))
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
        novo_cartao = _extrair(lead.cartao, entrada.conteudo)
        # quem já fechou um ciclo e volta com outra intenção começa uma oportunidade nova, não sobrescreve a antiga
        if (sucessora := nova_oportunidade_se_mudou_intencao(lead, novo_cartao.intencao)):
            auditar(acao="oportunidade.aberta", entidade="lead", entidade_id=sucessora.id, ator_tipo="agente",
                    ator_nome="Mora", dados={"anterior": lead.id, "cliente_id": lead.cliente_id,
                                              "de": str(lead.cartao.intencao), "para": str(novo_cartao.intencao)})
            # o cartão da nova oportunidade sai SÓ desta mensagem: o que ela procura agora é outra coisa,
            # mas o contato e o nome seguem sendo da mesma pessoa
            contato = {c: getattr(lead.cartao, c) for c in ("nome_informado", "telefone_informado", "email_informado")}
            sucessora.cartao = _extrair(CartaoQualificacao(), entrada.conteudo).model_copy(
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
        return {"lead": lead, "proximo": "consultor"}

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
    prompt = carregar("qualificador", nome=lead.nome or "cliente", intencao=lead.cartao.intencao,
                      faltantes=lead.cartao.campos_faltantes() or ["nenhum"], contexto_origem=origem,
                      contexto_cobertura=cobertura, contexto_abertura=abertura,
                      contexto_contato=_contexto_contato(lead, state))
    msg = llm_conversa().invoke([prompt, *state["messages"]])

    opcoes = ["Comprar", "Alugar", "Investir"] if lead.cartao.intencao == Intencao.INDEFINIDA else []
    return {"lead": lead, "messages": [msg],
            "resposta": RespostaAgente(lead_id=lead.id, texto=sanear(msg.content, lead.id), opcoes=opcoes)}
