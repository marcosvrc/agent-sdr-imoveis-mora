"""Conversa humanizada que preenche o CartaoQualificacao. Extração estruturada (papel `extracao`) +
resposta (papel `conversa`)."""
import re

from langchain_core.messages import AIMessage
from pydantic import Field

from sdr_shared.db import ClienteRepository, auditar, nova_oportunidade_se_mudou_intencao
from sdr_shared.messaging import RespostaAgente
from sdr_shared.models import CartaoQualificacao, Estagio, Intencao, Segmento
from ..llm import llm_conversa, llm_extracao
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


# Pergunta de cada campo: o que dizer ao modelo que falta, e o texto fixo quando ele se perde.
PERGUNTA = {
    "intencao": ("se ele quer comprar, alugar ou investir", "Você quer comprar, alugar ou investir?"),
    "regiao": ("em que região ou bairro ele procura", "Em qual região ou bairro de São Paulo você procura?"),
    "preco_max": ("até quanto ele pretende pagar", "Até quanto você pretende pagar?"),
    "quartos": ("quantos quartos ele precisa", "Quantos quartos você precisa?"),
    "urgencia": ("para quando ele precisa (é urgente ou dá para esperar?)",
                 "E pra quando você precisa? É urgente ou dá pra ir com calma?"),
    "area_min": ("quantos metros quadrados ele precisa", "Quantos metros quadrados você precisa, mais ou menos?"),
    "perfil_investidor": ("o perfil dele como investidor (conservador, moderado ou arrojado)",
                          "Como você se define como investidor: mais conservador, moderado ou arrojado?"),
    "ticket": ("quanto ele pretende investir", "Quanto você pretende investir?"),
    "retorno_esperado": ("que retorno ele espera", "Que retorno você espera, mais ou menos?"),
}

# Promessa de busca que o qualificador não pode cumprir: quem mostra imóvel é o consultor, e só
# quando o cartão fecha. Um lead real ouviu "vou te apresentar as opções" com a urgência ainda em
# aberto — e ficou esperando uma mensagem que nunca veio.
PROMESSA = re.compile(r"\b(vou|vamos|deixa eu|deixe-me|já) (te |lhe )?(apresentar|mostrar|buscar|procurar|"
                      r"verificar|separar|trazer|levantar)\b|\bum (momento|minutinho|instante)\b|\bjá te mostro\b",
                      re.I)

_URG_SEM_PRAZO = re.compile(r"sem pressa|com calma|sem prazo|n[aã]o tenho pressa|sem urg[eê]ncia|n[aã]o (é|e) urgente|"
                            r"ano que vem|pr[oó]ximo ano|s[oó] pesquisando|s[oó] olhando", re.I)
_URG_IMEDIATA = re.compile(r"urg[eê]n|urgente|o quanto antes|imediat|pra ontem|para ontem|esse m[eê]s|este m[eê]s|"
                           r"\bj[aá]\b|r[aá]pido|logo", re.I)
_URG_3 = re.compile(r"\b(1|2|3|um|dois|tr[eê]s) m[eê]s", re.I)
_URG_6 = re.compile(r"\b(4|5|6|quatro|cinco|seis) meses|meio ano|semestre", re.I)
_FALA_DE_PRAZO = re.compile(r"urg[eê]n|prazo|quando|mudar|pressa", re.I)


_SEM_PREFERENCIA = re.compile(r"sem prefer|tanto faz|qualquer|n[aã]o importa|indiferente|sem restri", re.I)


def quartos_sem_preferencia(mensagem: str, pergunta: str = "") -> bool:
    """"sem preferência de quartos" é resposta, não silêncio. Sem isto o campo ficava vazio e a Mora
    perguntava os quartos de novo logo depois de dizer "deixo em aberto". Zero é "no mínimo zero":
    a busca não filtra por quartos."""
    return bool(_SEM_PREFERENCIA.search(mensagem)) and bool(re.search(r"quarto", f"{pergunta} {mensagem}", re.I))


def urgencia_por_regra(mensagem: str, pergunta: str = "") -> str | None:
    """Rede de segurança para a urgência, que o extrator às vezes deixa passar.

    "estou com uma urgencia", em resposta a "tem alguma urgência?", voltou sem urgência — e como ela
    é campo obrigatório, o cartão nunca fechava e os imóveis nunca apareciam. Só vale quando a
    mensagem ou a pergunta anterior falam de prazo: "logo" solto numa frase qualquer não é urgência.
    """
    if not (_FALA_DE_PRAZO.search(pergunta or "") or _FALA_DE_PRAZO.search(mensagem)):
        return None
    for regra, valor in ((_URG_SEM_PRAZO, "sem_prazo"), (_URG_6, "6_meses"), (_URG_3, "3_meses"),
                         (_URG_IMEDIATA, "imediata")):
        if regra.search(mensagem):
            return valor
    return None


def _vale(campo: str, valor) -> bool:
    """O modelo disse alguma coisa sobre este campo?"""
    if isinstance(valor, str) and not valor.strip():
        return False
    if valor is False:                                  # "não pediu visita" é o default, não um fato
        return False
    if valor in _NAO_INFORMADO:
        return False
    return not (valor == 0 and campo in _ZERO_NAO_VALE)


def _abertura(state) -> str:
    """Se a Mora se apresenta nesta resposta.

    Só na primeira mensagem — e nem nela quando o canal já mostrou a apresentação. O chat do site
    abre com uma bolha de boas-vindas da Mora antes de o cliente digitar; apresentar-se de novo
    na resposta ao "oi" fazia o cliente ler "Eu sou a Mora…" duas vezes seguidas.
    """
    if not state.get("primeira_interacao"):
        return "A conversa já está em andamento: não se apresente de novo nem repita boas-vindas."
    entrada = state.get("entrada")
    if entrada is not None and (entrada.meta or {}).get("saudacao_exibida"):
        return ("O cliente já viu a apresentação da Mora (nome e empresa) numa mensagem de boas-vindas "
                "do site, logo antes desta: NÃO se apresente de novo nem dê boas-vindas. Responda ao que "
                "ele disse e siga com a pergunta.")
    return ("Esta é a PRIMEIRA mensagem desta conversa: apresente-se em meia frase (Mora, da "
            "Vértice Imóveis) antes de perguntar.")


def _extrair(cartao: CartaoQualificacao, mensagem: str, pergunta: str = "") -> CartaoQualificacao:
    try:
        novo = llm_extracao().with_structured_output(Extracao).invoke(
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


_TELEFONE = re.compile(r"(?:\+?55\s*)?(?:\(?\d{2}\)?\s*)?9?\s*\d{4}[\s.-]?\d{4}")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def so_contato(txt: str) -> bool:
    """A mensagem é, essencialmente, um telefone ou um e-mail ("11 98765-4321", "meu zap é …")."""
    achado = _TELEFONE.search(txt) or _EMAIL.search(txt)
    if not achado:
        return False
    resto = (txt[:achado.start()] + txt[achado.end():]).strip()
    return len(resto.split()) <= 6          # "é esse", "meu whatsapp é", "pode ligar nesse" — nada além


def _contexto_contato_recebido(lead, state) -> str:
    """O cliente acabou de mandar o contato que a Mora pediu: agradecer e fechar, não vender de novo."""
    if not so_contato(state["entrada"].conteudo or ""):
        return ""
    if lead.estagio == Estagio.AGENDADO:
        quando = ""
        try:
            from sdr_shared.db import VisitaRepository
            if v := VisitaRepository().proxima_do_lead(lead.id):
                from ..tools.agenda import formatar
                quando = f" ({formatar(v)})"
        except Exception:
            pass
        return (f"O cliente acabou de mandar o contato que você pediu, e a visita dele já está reservada{quando}. "
                "Agradeça em meia frase, diga que o corretor vai falar com ele por esse contato para confirmar "
                "a visita e pergunte se pode ajudar em mais alguma coisa. Não repita o número nem o e-mail, "
                "e não ofereça imóveis nem horários.")
    return ("O cliente acabou de mandar o contato que você pediu. Agradeça em meia frase, diga que o corretor "
            "pode mandar fotos e detalhes por ali e pergunte se algum dos imóveis que você mostrou chamou a "
            "atenção. Não repita o número nem o e-mail e não liste imóveis de novo.")


def pede_nome_agora(lead, state) -> bool:
    """O nome se pede UMA vez, logo depois que o cliente diz o que quer (comprar, alugar, investir).

    Antes a instrução era "numa das próximas mensagens", sem momento definido — e o modelo nunca
    pedia: um lead reservou visita sem que a Mora soubesse como chamá-lo. Só no site: no Telegram o
    nome vem do perfil.
    """
    from sdr_shared.messaging import Canal
    return (state["entrada"].canal == Canal.WEB and not lead.nome and not state.get("pediu_nome")
            and lead.cartao.intencao != Intencao.INDEFINIDA)


CONTEXTO_NOME = ("Nesta resposta NÃO pergunte o próximo campo: confirme em meia frase o que ele disse e pergunte "
                 "só o primeiro nome, de forma leve ('E como posso te chamar?'). Se ele preferir não dizer, "
                 "tudo bem — na próxima você segue a qualificação.")


def _contexto_proxima(lead) -> str:
    faltam = lead.cartao.campos_faltantes()
    if not faltam or faltam[0] not in PERGUNTA:
        return ""
    return (f"A próxima informação que falta é {PERGUNTA[faltam[0]][0]}. Sua resposta termina com UMA pergunta "
            "sobre isso. Não pergunte nada fora da lista de campos — reforma, garagem, andar, onde ele mora "
            "hoje: isso o corretor vê depois.")


def _conferir(texto: str, lead, pedindo_nome: bool = False) -> str:
    """Com campo faltando, a resposta TEM de perguntar por ele, e não pode prometer imóveis.

    O modelo às vezes ignora a instrução: inventa uma pergunta fora da lista ou anuncia que vai
    mostrar as opções. As duas coisas deixam o cartão aberto para sempre. Aqui a correção é
    determinística: a pergunta certa, com o texto fixo do campo.
    """
    faltam = lead.cartao.campos_faltantes()
    if not faltam or faltam[0] not in PERGUNTA:
        return texto
    fixa = "E como posso te chamar?" if pedindo_nome else PERGUNTA[faltam[0]][1]
    if PROMESSA.search(texto):
        return f"Anotado! {fixa}"
    if "?" not in texto:
        return f"{texto.rstrip()}\n\n{fixa}"
    return texto


def _contexto_contato(lead, state) -> str:
    """Pedir contato cedo demais derruba a conversa; tarde demais perde o lead. A regra está aqui."""
    from sdr_shared.messaging import Canal
    if state["entrada"].canal != Canal.WEB:
        return ""                                   # no Telegram já temos identificador e nome do perfil
    if not lead.cartao.tem_contato() and lead.cartao.completo():
        return ("O cliente já disse o que procura. Ao apresentar as opções ou marcar algo, peça UM contato "
                "(telefone de preferência) explicando para quê: 'me passa seu telefone que te mando as fotos "
                "e o corretor confirma a visita'. Não insista se ele não quiser, e não peça e-mail junto.")
    return ""


# O valor que muda de escala com a intenção. "Até 800 mil" de compra não é "até 800 mil por mês" de
# aluguel, nem ticket de investimento: na troca, o teto antigo não pode atravessar.
_TETOS = ("preco_min", "preco_max", "ticket")


def run(state: AgentState) -> dict:
    lead, entrada = state["lead"], state["entrada"]
    fora_de_cobertura = None
    trocou = False
    if entrada.conteudo:
        pergunta = ultima_pergunta(state.get("messages"))
        novo_cartao = _extrair(lead.cartao, entrada.conteudo, pergunta)
        if not novo_cartao.urgencia and (urg := urgencia_por_regra(entrada.conteudo, pergunta)):
            novo_cartao = novo_cartao.model_copy(update={"urgencia": urg})
        if novo_cartao.quartos is None and quartos_sem_preferencia(entrada.conteudo, pergunta):
            novo_cartao = novo_cartao.model_copy(update={"quartos": 0})
        intencao_antes = lead.cartao.intencao
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
            # Troca de intenção sem oportunidade nova (lead ainda QUALIFICADO, não fechou ciclo): o
            # cartão é o mesmo, e o merge mantinha o teto da intenção antiga — compra até 800 mil
            # virava aluguel até R$ 800 mil por mês, e a busca seguia com ele. Teto que esta mensagem
            # não repetiu é o antigo, e cai; bairro e quartos seguem valendo (a pessoa é a mesma).
            if Intencao.INDEFINIDA not in (intencao_antes, novo_cartao.intencao) and novo_cartao.intencao != intencao_antes:
                novo_cartao = novo_cartao.model_copy(update={
                    c: None for c in _TETOS if getattr(novo_cartao, c) == getattr(lead.cartao, c)})
            lead.cartao = novo_cartao
        trocou = sucessora is not None or (intencao_antes != Intencao.INDEFINIDA
                                           and lead.cartao.intencao != intencao_antes)
        lead.cartao, fora_de_cobertura = _normalizar_local(lead.cartao, entrada.conteudo)
    _absorver_contato(lead)
    if lead.estagio == Estagio.NOVO and lead.cartao.intencao != Intencao.INDEFINIDA:
        lead.estagio = Estagio.QUALIFICANDO

    # Trocou de intenção: os imóveis mostrados eram da busca antiga (compra), e contavam como "já
    # sugeridos" — o cartão do aluguel fechava e a busca nova não rodava, porque o consultor só é
    # chamado direto quando ainda não há sugestão. Zerados, a busca da intenção nova roda quando o
    # cartão fechar. O histórico de interesses (banco) continua lá.
    recomeco = ({"imoveis_sugeridos": [], "ultimos_sugeridos": [], "ajuste": None, "ajuste_pendente": None,
                 "imovel_escolhido": None, "horarios_oferecidos": [], "slots_crm": {},
                 "horario_pendente": None, "contato_insistido": False} if trocou else {})
    sugeridos = [] if trocou else state.get("imoveis_sugeridos")

    # Cartão ficou completo com esta mensagem: não prometer "vou buscar" — o consultor responde já com os imóveis.
    # (O supervisor decidiu antes da extração; sem isto o modelo inventa uma "ferramenta" em texto.)
    if lead.cartao.completo() and not sugeridos:
        # `cartao_extraido_de`: o consultor recebe o turno agora e leria esta mesma frase de novo.
        return {"lead": lead, "proximo": "consultor", "cartao_extraido_de": entrada.conteudo, **recomeco}

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
    pedindo_nome = pede_nome_agora(lead, state)
    abertura = _abertura(state)
    prompt = carregar("qualificador", memoria=lead.resumo, nome=lead.nome or "cliente", intencao=lead.cartao.intencao,
                      faltantes=lead.cartao.campos_faltantes() or ["nenhum"], contexto_origem=origem,
                      contexto_cobertura=cobertura, contexto_abertura=abertura,
                      contexto_contato=_contexto_contato_recebido(lead, state) or _contexto_contato(lead, state),
                      contexto_proxima=CONTEXTO_NOME if pedindo_nome else _contexto_proxima(lead))
    msg = llm_conversa().invoke([prompt, *state["messages"]])
    texto_final = _conferir(sanear(msg.content, lead.id), lead, pedindo_nome)
    if texto_final != sanear(msg.content, lead.id):
        msg = AIMessage(content=texto_final)

    opcoes = ["Comprar", "Alugar", "Investir"] if lead.cartao.intencao == Intencao.INDEFINIDA else []
    return {"lead": lead, "messages": [msg], **({"pediu_nome": True} if pedindo_nome else {}), **recomeco,
            "resposta": RespostaAgente(lead_id=lead.id, texto=texto_final, opcoes=opcoes)}
