"""Entrada do agente: recebe MensagemNormalizada, roda o grafo, persiste, despacha ao canal, agenda follow-up."""
import logging
import re
import time
import traceback

from sdr_shared.db import (LeadRepository, MensagemRepository, EventoNavegacaoRepository, CanalRepository,
                           InteresseRepository,
                           auditar, notificar, registrar_turno)
from sdr_shared.crm import publicar_turno as publicar_no_crm
from sdr_shared.crm import reconhecer
from sdr_shared.log import configurar as configurar_log, contexto, limpar_contexto
from sdr_shared.messaging import MensagemNormalizada, TipoMensagem, Canal, INICIADAS_PELO_AGENTE
from sdr_shared.models import Lead, Estagio
from .graph import build_graph, build_checkpointer, caminho_atual, novo_caminho
from .guardrails import vazao
from .dispatch import cancelar_followup, despachar, publicar_eventos, reagendar_followup
from .scoring import calcular, respondeu_rapido

configurar_log("agent")           # JSON fora do local: dá para consultar campo a campo
log = logging.getLogger("agent")

_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph(build_checkpointer())
    return _graph


def _carregar_lead(entrada: MensagemNormalizada) -> tuple[Lead, bool]:
    repo = LeadRepository()
    lead = repo.get(entrada.lead_id)
    novo = lead is None
    if novo:
        lead = repo.upsert(Lead(id=entrada.lead_id, nome=entrada.meta.get("nome"), telefone=entrada.meta.get("telefone")))
        CanalRepository().vincular(lead.id, entrada.canal, entrada.identificador_canal)
    # Contexto de origem: botão do site (IMOVEL-xxx) e imóveis navegados na sessão web
    origem = [x for x in [entrada.meta.get("imovel_origem")] if x]
    if entrada.canal == Canal.WEB:
        origem += EventoNavegacaoRepository().imoveis_vistos(entrada.identificador_canal)
    if origem:
        lead.cartao.imoveis_visualizados = list(dict.fromkeys(lead.cartao.imoveis_visualizados + origem))
    # Clicar em "falar sobre este imóvel" é interesse DECLARADO — diferente de ter passado os olhos
    # na ficha, que fica só em `imoveis_visualizados`. Por isso só o `imovel_origem` vira interesse.
    if declarado := entrada.meta.get("imovel_origem"):
        try:
            InteresseRepository().registrar(lead.id, declarado, situacao="interessado", origem="site")
        except Exception:
            log.warning("não consegui registrar o interesse declarado do lead %s", lead.id, exc_info=True)
    return lead, novo


def _avisar_que_ouviu(entrada: MensagemNormalizada) -> None:
    """Recibo imediato do áudio, antes de transcrever.

    Transcrever leva segundos — baixar o arquivo, rodar o modelo — e nesse intervalo o cliente vê
    silêncio. Silêncio depois de mandar um áudio se parece com falha, e a reação natural é mandar
    de novo, ou desistir. Uma linha resolve, e ela não entra no histórico da conversa: é recibo de
    entrega, não fala da Mora sobre o assunto, e no prompt do próximo turno só atrapalharia.

    Se o motor está desligado não se promete nada — o cliente vai receber o pedido para escrever.
    """
    from .tools.transcricao import _motor_efetivo
    try:
        if _motor_efetivo() == "off":
            return
        from sdr_shared.messaging import RespostaAgente
        despachar(entrada.canal, entrada.identificador_canal,
                  RespostaAgente(lead_id=entrada.lead_id,
                                 texto="Recebi seu áudio, só um instante que já te respondo."))
    except Exception:
        # O recibo é cortesia: falhar aqui não pode impedir a transcrição, que é o que importa.
        log.warning("não consegui avisar o lead %s de que o áudio chegou", entrada.lead_id, exc_info=True)


def _transcrever_se_audio(entrada: MensagemNormalizada) -> MensagemNormalizada:
    if entrada.tipo == TipoMensagem.AUDIO and not entrada.conteudo:
        _avisar_que_ouviu(entrada)
        try:
            from .tools.transcricao import transcrever
            entrada.conteudo = transcrever(entrada.meta)
        except Exception:
            # Com log, e não só com o texto de degradação. O cliente recebe "não entendi o áudio"
            # de qualquer jeito — mas quem opera precisa saber SE foi o motor faltando na imagem,
            # o download do modelo, o token do canal ou o áudio em si. Sem esta linha, a única
            # pista era a frase de desculpa, que é igual para as quatro causas.
            log.exception("falha ao transcrever o áudio do lead %s", entrada.lead_id)
            entrada.conteudo = "(áudio não compreendido — peça para o cliente escrever)"
    return entrada


def processar(entrada: MensagemNormalizada) -> None:
    t0 = time.perf_counter()
    entrada = _transcrever_se_audio(entrada)
    novo_caminho()
    limpar_contexto()
    contexto(lead_id=entrada.lead_id, canal=str(entrada.canal.value), tipo=str(entrada.tipo.value))

    def _fim(resultado: str, lead_=None) -> None:
        """Um INSERT por turno com o tempo que o CLIENTE esperou — inclusive quando o turno morre
        cedo. Sem registrar as saídas antecipadas, a taxa de falha ficaria sempre em zero."""
        registrar_turno(lead_id=entrada.lead_id, canal=str(entrada.canal.value), resultado=resultado,
                        duracao_ms=int((time.perf_counter() - t0) * 1000),
                        estagio=str(lead_.estagio.value) if lead_ is not None else None,
                        nos=caminho_atual())

    # Sem barramento não há como entregar a resposta. Descobrir isso no fim — depois do modelo,
    # do lead gravado e do histórico registrado — era a pior hora: o trabalho estava feito e a
    # resposta se perdia em silêncio. Um PING antes de tudo falha alto e barato; a mensagem fica
    # pendente no stream e é retomada quando o worker volta (ver `_retomar_pendentes`).
    if not _barramento_responde():
        _fim("barramento")
        raise RuntimeError("barramento indisponível: turno não iniciado para não perder a resposta")

    # Turno que a Mora começa (follow-up, aviso de imóvel novo) não é o cliente digitando: não
    # passa pela vazão, não entra no histórico como mensagem recebida e não carimba atividade.
    iniciada_pelo_agente = entrada.tipo in INICIADAS_PELO_AGENTE
    if not iniciada_pelo_agente and not _dentro_da_vazao(entrada):
        _fim("vazao")
        return

    lead, novo = _carregar_lead(entrada)
    estagio_antes = lead.estagio
    # medido ANTES de marcar a atividade: depois disso o carimbo antigo se perde
    rapido = not iniciada_pelo_agente and respondeu_rapido(lead.ultima_mensagem_em)
    msgs = MensagemRepository()
    id_entrada = None
    if not iniciada_pelo_agente:
        id_entrada = msgs.registrar(lead.id, entrada.canal, "in", entrada.conteudo, entrada.meta)
        LeadRepository().marcar_atividade(lead.id)

    # Handoff ativo: o corretor responde pelo painel; o agente não fala (mas registra, avisa e resume)
    if lead.estagio == Estagio.HANDOFF and not iniciada_pelo_agente:
        cancelar_followup(lead.id)           # o cliente está falando: nada de follow-up por cima
        quem = lead.nome or lead.telefone or lead.id
        voltou = PEDE_MORA.search(entrada.conteudo or "") and _devolver_a_mora(lead, entrada)
        if not voltou:
            notificar(tipo="lead.respondeu", corretor_id=lead.corretor_id, lead_id=lead.id,
                      titulo=f"{quem} respondeu", detalhe=(entrada.conteudo or "")[:160] or None,
                      chave=str(int(time.time()) // 900))   # no máximo um aviso por lead a cada 15 min
            _avisar_que_o_corretor_foi_chamado(lead, entrada, msgs)
            _fim("handoff", lead)
            return

    # Governança: orçamento muito acima do teto → não chama modelo, encaminha ao corretor.
    if not iniciada_pelo_agente and _bloqueado_por_orcamento(lead, entrada):
        _fim("orcamento", lead)
        return

    # Antes de perguntar, ver se o CRM já sabe. Um cliente que falou com um corretor na semana
    # passada não deve recomeçar do zero — e perguntar de novo o que ele já respondeu é o que faz um
    # atendimento automático parecer automático. Só preenche campo vazio: o que ele disser agora
    # continua valendo mais que o registro. Silencioso quando não há CRM, quando o contato é
    # desconhecido ou quando já procuramos por este contato.
    if reconhecer(lead):
        LeadRepository().upsert(lead)           # era `.salvar`, que não existe: achado pelo pyright

    # O histórico guarda o que o cliente VIU, não o protocolo do botão: ver `texto_para_historico`.
    # `entrada.conteudo` segue cru para os nós, que é quem precisa do identificador.
    from .nodes.agendador import texto_para_historico
    entrada_grafo = {"lead": lead, "entrada": entrada, "primeira_interacao": novo, "saltos": 0, "resposta": None,
                     "cartao_extraido_de": None, "ultimo_no": None,
                     "messages": [("user", texto_para_historico(entrada.conteudo))] if entrada.conteudo else []}
    try:
        out = get_graph().invoke(entrada_grafo, config={"configurable": {"thread_id": lead.id}})
    except Exception:
        # Modelo fora do ar, timeout, erro de nó: o cliente não pode ficar esperando em silêncio.
        log.exception("falha ao processar o turno do lead %s — respondendo com fallback", lead.id)
        auditar(acao="agente.turno_falhou", entidade="lead", entidade_id=lead.id, ator_tipo="agente",
                ator_nome="Mora", origem=str(entrada.canal.value), resultado="erro",
                detalhe=traceback.format_exc(limit=3)[-900:], dados={"estagio": str(estagio_antes.value)})
        _fim("erro", lead)
        _responder_falha(lead, entrada)
        return

    lead = out["lead"]
    lead.score, lead.temperatura = calcular(lead, respondeu_rapido=rapido)
    # preservar_handoff: se o corretor clicou "Assumir" enquanto o turno rodava, o estágio e o
    # corretor que ele gravou valem mais que os que este turno leu lá no começo.
    lead = LeadRepository().upsert(lead, preservar_handoff=True)

    if lead.estagio != estagio_antes:
        auditar(acao="lead.estagio_alterado", entidade="lead", entidade_id=lead.id, ator_tipo="agente",
                ator_nome="Mora", origem=str(entrada.canal.value),
                dados={"de": str(estagio_antes.value), "para": str(lead.estagio.value),
                       "temperatura": str(lead.temperatura), "score": lead.score})
    id_saida = None
    resposta = out.get("resposta")
    if resposta:
        id_saida = msgs.registrar(lead.id, entrada.canal, "out", resposta.texto, {"opcoes": resposta.opcoes, "imoveis": [c.id for c in resposta.imoveis]})
        despachar(entrada.canal, entrada.identificador_canal, resposta)
    publicar_eventos(lead, estagio_antes)
    # Espelha no CRM o que a conversa produziu (docs/decisions.md, D-01). Depois do despacho de
    # propósito: o cliente já recebeu a resposta, então nada aqui atrasa o atendimento — e a função
    # engole a própria falha, porque um CRM fora do ar não pode virar um atendimento fora do ar.
    publicar_no_crm(lead, entrada, texto_saida=resposta.texto if resposta else None,
                    estagio_antes=estagio_antes, id_entrada=id_entrada, id_saida=id_saida,
                    imoveis=resposta.imoveis if resposta else None)
    reagendar_followup(lead, entrada.canal, entrada.identificador_canal)
    # Reativação sai separada em `turnos`: é a métrica da fase 4 (quantos avisos viraram conversa),
    # e misturada com "ok" ela seria indistinguível de um turno pedido pelo cliente.
    _fim("reativacao" if entrada.tipo == TipoMensagem.REATIVACAO else "ok", lead)
    log.info("turno concluído", extra={"campos": {
        "duracao_ms": int((time.perf_counter() - t0) * 1000), "estagio": str(lead.estagio.value),
        "nos": caminho_atual(), "cartao_faltam": lead.cartao.campos_faltantes(),
        "temperatura": str(lead.temperatura), "score": lead.score}})


def _barramento_responde() -> bool:
    """`ping` é opcional na porta: dublês de teste e brokers em memória não o têm, e para eles a
    resposta é sempre sim."""
    from . import dispatch                       # a mesma porta que o despacho usa (e que os testes trocam)
    ping = getattr(dispatch.get_broker(), "ping", None)
    if ping is None:
        return True
    try:
        ping()
        return True
    except Exception:
        log.error("barramento não responde; turno do lead recusado antes de começar", exc_info=True)
        return False


def _dentro_da_vazao(entrada: MensagemNormalizada) -> bool:
    """Excesso de mensagens não vira turno de modelo; o cliente é avisado uma vez e a conversa segue."""
    pode, avisar = vazao.permitir(entrada.lead_id)
    if pode:
        return True
    log.warning("vazão excedida lead=%s canal=%s", entrada.lead_id, entrada.canal)
    auditar(acao="agente.vazao_excedida", entidade="lead", entidade_id=entrada.lead_id, ator_tipo="sistema",
            ator_nome="guardrails", origem=str(entrada.canal.value), resultado="erro",
            detalhe="limite de mensagens por janela", dados={"avisou": avisar})
    if avisar:
        from sdr_shared.messaging import RespostaAgente
        try:
            despachar(entrada.canal, entrada.identificador_canal,
                      RespostaAgente(lead_id=entrada.lead_id, texto=vazao.AVISO))
        except Exception:
            log.exception("falha ao avisar o lead %s sobre a vazão", entrada.lead_id)
    return False


# Pedido EXPLÍCITO de voltar para a assistente. Só isso tira o lead do corretor — "oi" ou "e aí?"
# não tiram, porque handoff existe para quem quis uma pessoa.
PEDE_MORA = re.compile(
    r"(\b(volt|continu|segu)\w*\b[^.!?]{0,24}\b(mora|assistente|rob[ôo]|bot|virtual|ia)\b"
    r"|\bfalar com a mora\b|\bquero (a mora|o bot|a assistente)\b"
    r"|\bn[ãa]o quero (mais )?(falar com )?(o |um |a )?(corretor|humano|atendente|pessoa)\b"
    r"|\bcancela(r)? o (atendimento )?(humano|corretor)\b)", re.I)

AVISO_ESPERA = "handoff_aviso"


def _devolver_a_mora(lead: Lead, entrada: MensagemNormalizada) -> bool:
    """O cliente pediu a assistente de volta. Devolve e deixa o turno seguir normalmente.

    Sem isto, handoff é uma porta de mão única: a Mora cala, e quem caiu lá por engano — um "dim"
    que o roteador leu como assunto fora de imóveis — não tem como pedir para voltar. O corretor
    continua sabendo de tudo (fica avisado, e o histórico é o mesmo); o que muda é quem responde
    agora.
    """
    lead.estagio = Estagio.QUALIFICADO if lead.cartao.completo() else Estagio.QUALIFICANDO
    LeadRepository().upsert(lead)
    auditar(acao="lead.devolvido_ao_agente", entidade="lead", entidade_id=lead.id, ator_tipo="cliente",
            ator_nome=lead.nome or lead.id, origem=str(entrada.canal.value), resultado="ok",
            detalhe="o cliente pediu para continuar com a Mora",
            dados={"corretor_id": lead.corretor_id, "para": str(lead.estagio.value)})
    notificar(tipo="lead.devolvido", corretor_id=lead.corretor_id, lead_id=lead.id,
              titulo=f"{lead.nome or lead.id} preferiu seguir com a Mora",
              detalhe="O cliente pediu para continuar com a assistente. A conversa segue no painel.",
              chave=f"devolvido-{int(time.time()) // 900}")
    log.info("lead %s devolvido ao agente a pedido do cliente", lead.id)
    return True


def _avisar_que_o_corretor_foi_chamado(lead: Lead, entrada: MensagemNormalizada, msgs) -> None:
    """Uma única mensagem enquanto ninguém da equipe respondeu — e nunca por cima do corretor.

    O silêncio total era o que transformava um handoff acidental em beco: o cliente escrevia, nada
    acontecia, e não havia nada na tela dizendo o que esperar nem como sair. Aqui ele fica sabendo
    que o corretor foi avisado e que pode continuar com a Mora se preferir. Se o corretor já falou,
    esta função não abre a boca: interromper quem está atendendo seria pior que o silêncio.
    """
    historico = msgs.historico(lead.id, limite=30)
    for m in reversed(historico):
        if m["direcao"] == "corretor":
            return                                    # a equipe já está na conversa
        if (m.get("meta") or {}).get("motivo") == AVISO_ESPERA:
            return                                    # já avisamos uma vez neste handoff
    nome = f", {lead.nome.split()[0]}" if lead.nome else ""
    from sdr_shared.db import CorretorRepository
    responsavel = CorretorRepository().get(lead.corretor_id) if lead.corretor_id else None
    corretor = responsavel.nome.split()[0] if responsavel else None
    texto = (f"Recebi sua mensagem{nome}! "
             + (f"{corretor} já foi avisada e responde por aqui mesmo. " if corretor
                else "Um corretor da equipe já foi avisado e responde por aqui mesmo. ")
             + "Se preferir continuar comigo enquanto isso, é só dizer \"continuar com a Mora\".")
    from sdr_shared.messaging import RespostaAgente
    try:
        msgs.registrar(lead.id, entrada.canal, "out", texto, {"motivo": AVISO_ESPERA})
        despachar(entrada.canal, entrada.identificador_canal,
                  RespostaAgente(lead_id=lead.id, texto=texto))
    except Exception:
        log.exception("falha ao avisar o lead %s de que o corretor foi chamado", lead.id)


def _responder_falha(lead: Lead, entrada: MensagemNormalizada) -> None:
    """Último recurso: avisa o cliente com honestidade e passa para um corretor humano."""
    from sdr_shared.messaging import RespostaAgente, Acao
    from .nodes.handoff import escolher_corretor
    estagio_antes = lead.estagio
    try:
        corretor = escolher_corretor(lead)
        lead.estagio = Estagio.HANDOFF
        LeadRepository().upsert(lead)
    except Exception:
        corretor = None
        log.exception("falha também ao encaminhar o lead %s ao corretor", lead.id)
    texto = ("Tive um problema técnico aqui e não consegui concluir sua busca. "
             + (f"Já avisei {corretor.split()[0]}, da nossa equipe, que continua com você em instantes."
                if corretor else "Já avisei um corretor da nossa equipe, que continua com você em instantes."))
    try:
        MensagemRepository().registrar(lead.id, entrada.canal, "out", texto, {"motivo": "falha_agente"})
        despachar(entrada.canal, entrada.identificador_canal, RespostaAgente(lead_id=lead.id, texto=texto, acao=Acao.HANDOFF))
        publicar_eventos(lead, estagio_antes)
    except Exception:
        log.exception("falha ao despachar a mensagem de fallback do lead %s", lead.id)


def _bloqueado_por_orcamento(lead: Lead, entrada: MensagemNormalizada) -> bool:
    from sdr_shared.ports import modo_do_agente
    if modo_do_agente() != "bloqueado":
        return False
    from sdr_shared.messaging import RespostaAgente, Acao
    from .nodes.handoff import escolher_corretor
    estagio_antes = lead.estagio
    corretor = escolher_corretor(lead)
    lead.estagio = Estagio.HANDOFF
    LeadRepository().upsert(lead)
    auditar(acao="agente.bloqueado_por_orcamento", entidade="lead", entidade_id=lead.id, ator_tipo="sistema",
            ator_nome="governanca", origem=str(entrada.canal.value), resultado="erro",
            detalhe="orçamento de tokens acima do teto — turno encaminhado ao corretor",
            dados={"corretor_id": lead.corretor_id, "estagio_antes": str(estagio_antes.value)})
    texto = (f"Vou chamar {corretor.split()[0]} para continuar com você agora mesmo." if corretor
             else "Vou chamar um corretor para continuar com você agora mesmo.")
    resposta = RespostaAgente(lead_id=lead.id, texto=texto, acao=Acao.HANDOFF)
    MensagemRepository().registrar(lead.id, entrada.canal, "out", texto, {"motivo": "orcamento_llm"})
    despachar(entrada.canal, entrada.identificador_canal, resposta)
    publicar_eventos(lead, estagio_antes)
    log.warning("orçamento de LLM estourado: lead %s encaminhado ao corretor sem chamar modelo", lead.id)
    return True


def resumir(lead_id: str) -> str | None:
    """Chamado por evento lead.stage_changed (agendado/handoff): gera briefing fora da conversa."""
    lead = LeadRepository().get(lead_id)
    if not lead:
        return None
    out = get_graph().invoke({"lead": lead, "entrada": MensagemNormalizada(lead_id=lead_id, canal=Canal.SISTEMA, identificador_canal=lead_id,
                                                                            tipo=TipoMensagem.TEXTO, conteudo=""),
                              "proximo": "resumidor", "saltos": 0, "resposta": None, "messages": []},
                             config={"configurable": {"thread_id": lead_id}})
    LeadRepository().upsert(out["lead"])
    return out["lead"].resumo


def local_worker():
    """Worker consumindo o tópico inbound do Redis."""
    from sdr_shared.db import iniciar_batimento
    from sdr_shared.ports import get_broker

    iniciar_batimento("agent")

    def ao_falhar(body: str, _erro: Exception) -> None:
        """Rede de segurança do worker: mesmo que `processar` estoure antes do try interno, o cliente recebe algo."""
        try:
            entrada = MensagemNormalizada.model_validate_json(body)
            lead = LeadRepository().get(entrada.lead_id) or Lead(id=entrada.lead_id)
            _responder_falha(lead, entrada)
        except Exception:
            log.exception("não foi possível avisar o cliente sobre a falha")

    get_broker().consume("inbound", lambda body: processar(MensagemNormalizada.model_validate_json(body)), ao_falhar=ao_falhar)
