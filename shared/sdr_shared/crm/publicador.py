"""Publica no CRM o que a conversa produziu.

Chamado ao fim de cada turno do agente. Três compromissos, e nenhum deles é negociável:

1. **Não derruba o turno.** Toda entrada aqui é embrulhada: se o CRM cair, o cliente continua
   recebendo resposta e a falha vira uma linha de log. Um CRM indisponível não pode virar um
   atendimento indisponível.
2. **Não inventa.** Oportunidade só é aberta quando a intenção está clara; preferências só sobem
   com o que o cliente disse; estágio só avança até `qualified`, que é o limite do agente.
3. **Repetir é seguro.** Cada ação lógica tem `operation_id` estável, derivado do lead e do fato —
   não de um contador nem do relógio. Republicar o mesmo turno não cria nada novo.
"""
import hashlib
import logging
from datetime import UTC, datetime

from ..messaging import MensagemNormalizada
from ..models import Estagio, Lead
from ..ports import get_crm
from . import traducao, vinculo

log = logging.getLogger("crm")


def habilitado() -> bool:
    """Há CRM configurado? Continua exportado porque chamadores fora daqui perguntam isso antes de
    montar dados que só o CRM consome."""
    return get_crm().habilitado()


def publicar_turno(lead: Lead, entrada: MensagemNormalizada, *, texto_saida: str | None = None,
                   estagio_antes: Estagio | None = None, id_entrada: int | None = None,
                   id_saida: int | None = None) -> None:
    """Ponto único de entrada. Nunca levanta exceção.

    `id_entrada` e `id_saida` são os ids das mensagens no banco da Mora; viram o
    `external_event_id` no CRM.
    """
    crm = get_crm()
    if not crm.habilitado():
        return
    try:
        with crm.sessao() as s:
            _publicar(s, lead, entrada, texto_saida, estagio_antes, id_entrada, id_saida)
    except Exception:
        log.warning("falha ao publicar o lead %s no CRM — a conversa segue", lead.id, exc_info=True)


def _publicar(s, lead: Lead, entrada: MensagemNormalizada, texto_saida: str | None,
              estagio_antes: Estagio | None, id_entrada: int | None = None,
              id_saida: int | None = None) -> None:
    v = vinculo.buscar(lead.id) or _abrir(s, lead)
    if v is None:
        return          # intenção ainda indefinida: não há oportunidade a abrir

    _registrar_conversa(s, v, lead, entrada, texto_saida, id_entrada, id_saida)
    versao = _atualizar_preferencias(s, v, lead)
    _mover(s, v, lead, versao, estagio_antes)

    # Encaminhamento entra por aqui, e não pelo nó do grafo, porque só no fim do turno o lead já
    # foi persistido e o estágio anterior ainda é conhecido. No nó, uma falha do CRM abortaria a
    # resposta que o cliente está esperando.
    if lead.estagio == Estagio.HANDOFF and estagio_antes != Estagio.HANDOFF:
        _encaminhar(s, v, lead)


def _abrir(s, lead: Lead) -> vinculo.Vinculo | None:
    """Cria cliente e oportunidade no CRM na primeira vez que a intenção fica clara.

    Esperar a intenção é deliberado: uma oportunidade precisa de propósito (aluguel ou compra), e
    abrir uma "de compra" para quem só disse "oi" encheria o funil do corretor de intenção
    inventada.
    """
    if traducao.proposito(lead) is None:
        return None

    crm_lead_id = s.garantir_lead(lead)
    if not crm_lead_id:
        return None
    aberta = s.garantir_oportunidade(lead, crm_lead_id)
    if not aberta:
        return None
    return vinculo.salvar(lead.id, crm_lead_id, aberta[0], aberta[1])


def _evento(lead_id: str, direcao: str, id_mensagem: int | None, texto: str) -> str:
    """Identificador da mensagem para o CRM.

    O id da linha em `mensagens` é a primeira escolha: é único, estável e sobrevive a republicação.
    Sem ele (chamada fora do handler), caímos num hash que inclui o LEAD — e essa palavra é o
    conserto de um defeito real: com o hash só do texto, dois clientes diferentes que escrevessem
    "oi" no mesmo canal colidiriam no índice único do CRM, e a mensagem do segundo entraria no
    histórico do primeiro. Apareceu ao rodar a suíte duas vezes.
    """
    if id_mensagem is not None:
        return f"mora-msg-{id_mensagem}"
    marca = hashlib.sha256(f"{lead_id}:{direcao}:{texto}".encode()).hexdigest()[:20]
    return f"mora-{direcao}-{marca}"


def _registrar_conversa(s, v: vinculo.Vinculo, lead: Lead,
                        entrada: MensagemNormalizada, texto_saida: str | None,
                        id_entrada: int | None = None, id_saida: int | None = None) -> None:
    """Uma interação para o que entrou e outra para o que saiu.

    O `external_event_id` é o que impede duplicata quando o mesmo turno é republicado: o CRM
    devolve o registro original em vez de criar uma segunda linha no histórico do cliente.
    """
    quando = datetime.now(UTC).isoformat()

    canal = str(entrada.canal.value)
    for direcao, rotulo, texto, id_msg in (("in", "inbound", entrada.conteudo, id_entrada),
                                           ("out", "outbound", texto_saida, id_saida)):
        if not texto:
            continue
        s.registrar_interacao(v.crm_lead_id, crm_opportunity_id=v.crm_opportunity_id, canal=canal,
                              direcao=rotulo, texto=texto, quando=quando,
                              evento_externo=_evento(lead.id, direcao, id_msg, texto))


def _atualizar_preferencias(s, v: vinculo.Vinculo, lead: Lead) -> int:
    """Devolve a versão atual da oportunidade — que é a precondição do próximo passo.

    Em 412 (alguém editou pelo painel no meio do caminho) relê a oportunidade e tenta uma vez. Isso
    é convivência normal com um corretor trabalhando, não recuperação de erro: por isso UMA
    retentativa, e não um laço.
    """
    versao = s.atualizar_preferencias(v.crm_opportunity_id, lead, v.crm_version)
    if versao is None:
        return v.crm_version        # o adaptador já registrou o motivo
    vinculo.atualizar_versao(lead.id, versao)
    return versao


def _mover(s, v: vinculo.Vinculo, lead: Lead, versao: int,
           estagio_antes: Estagio | None) -> None:
    """Move o estágio no CRM UM passo por vez, respeitando a tabela de transições de lá.

    A Mora pode saltar de `novo` para `qualificado` num turno só (o cliente despejou tudo na
    primeira mensagem); o CRM não aceita salto. Então percorremos o caminho — e quando a
    qualificação é recusada por falta de dado, isso não é erro: é o CRM dizendo que o cartão ainda
    está incompleto, que é a mesma coisa que a Mora já sabe.
    """
    destino = traducao.ESTAGIO.get(lead.estagio)
    if destino is None or destino == traducao.ESTAGIO.get(estagio_antes):
        return

    caminho = ["in_service", "qualified"]
    alvo = caminho.index(destino) if destino in caminho else -1
    if alvo < 0:
        return

    for passo in caminho[:alvo + 1]:
        nova = s.mover_estagio(v.crm_opportunity_id, destino=passo, versao=versao)
        if nova is None:
            # Recusa de um passo não interrompe o caminho: `INVALID_TRANSITION` significa que a
            # oportunidade já está nesse estágio ou além dele, e é o caso mais comum aqui. O
            # adaptador já distinguiu recusa esperada de falha no log.
            continue
        versao = nova
        vinculo.atualizar_versao(lead.id, versao)


def _encaminhar(s, v: vinculo.Vinculo, lead: Lead) -> None:
    """O resumo é o que o corretor lê antes de ligar. Usamos o que a Mora já escreveu; sem resumo
    ainda, o cartão de qualificação é a melhor descrição disponível — bem melhor que 'sem resumo'."""
    c = lead.cartao
    resumo = lead.resumo or "; ".join(
        x for x in [f"intenção: {c.intencao}", c.regiao and f"região: {c.regiao}",
                    c.bairros and f"bairros: {', '.join(str(b) for b in c.bairros)}",
                    c.preco_max and f"até R$ {c.preco_max:,.0f}".replace(",", "."),
                    c.quartos and f"{c.quartos} quarto(s)", c.urgencia and f"urgência: {c.urgencia}"]
        if x)
    s.encaminhar(v.crm_lead_id, v.crm_opportunity_id,
                 motivo=f"lead {lead.temperatura} encaminhado pela Mora",
                 resumo=resumo[:4000] or "Cliente pediu falar com uma pessoa.")


def publicar_encaminhamento(lead: Lead, motivo: str, resumo: str) -> None:
    """Passa o atendimento ao corretor NO CRM quando a Mora encaminha.

    Sem isto, o corretor veria no CRM uma oportunidade que o agente ainda conduz, enquanto na
    verdade a conversa já está com ele — e a ficha diria a coisa errada exatamente no momento em
    que alguém vai agir sobre ela.
    """
    crm = get_crm()
    if not crm.habilitado():
        return
    try:
        v = vinculo.buscar(lead.id)
        if v is None:
            return
        with crm.sessao() as s:
            s.encaminhar(v.crm_lead_id, v.crm_opportunity_id, motivo=motivo[:300],
                         resumo=(resumo or motivo)[:4000])
    except Exception:
        log.warning("falha ao encaminhar o lead %s no CRM", lead.id, exc_info=True)
