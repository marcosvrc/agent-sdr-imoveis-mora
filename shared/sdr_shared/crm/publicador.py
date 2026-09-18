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
from . import traducao, vinculo
from .cliente import ClienteCRM, habilitado

log = logging.getLogger("crm")

# Recusas que são o CRM funcionando, não falhando: com o atendimento em mãos humanas ou o contato
# bloqueado, é ESPERADO que a escrita não passe. Sobem como debug para não poluir o log de erro.
ESPERADOS = frozenset({"HUMAN_IN_CONTROL", "CONTACT_BLOCKED", "FORBIDDEN",
                       "QUALIFICATION_INCOMPLETE", "INVALID_TRANSITION"})


def _op(lead_id: str, acao: str, marca: str = "") -> str:
    """Identificador ESTÁVEL da ação lógica.

    Deriva do lead e do fato, nunca do relógio nem de um aleatório: é isso que faz a repetição da
    mesma publicação, num turno seguinte ou depois de um timeout, encontrar o registro já gravado
    em vez de criar um segundo.
    """
    digest = hashlib.sha256(f"{lead_id}:{acao}:{marca}".encode()).hexdigest()[:24]
    return f"mora-{acao}-{digest}"


def publicar_turno(lead: Lead, entrada: MensagemNormalizada, *, texto_saida: str | None = None,
                   estagio_antes: Estagio | None = None, id_entrada: int | None = None,
                   id_saida: int | None = None) -> None:
    """Ponto único de entrada. Nunca levanta exceção.

    `id_entrada` e `id_saida` são os ids das mensagens no banco da Mora; viram o
    `external_event_id` no CRM.
    """
    if not habilitado():
        return
    try:
        _publicar(lead, entrada, texto_saida, estagio_antes, id_entrada, id_saida)
    except Exception:
        log.warning("falha ao publicar o lead %s no CRM — a conversa segue", lead.id, exc_info=True)


def _publicar(lead: Lead, entrada: MensagemNormalizada, texto_saida: str | None,
              estagio_antes: Estagio | None, id_entrada: int | None = None,
              id_saida: int | None = None) -> None:
    crm = ClienteCRM()
    v = vinculo.buscar(lead.id) or _abrir(crm, lead)
    if v is None:
        return          # intenção ainda indefinida: não há oportunidade a abrir

    _registrar_conversa(crm, v, lead, entrada, texto_saida, id_entrada, id_saida)
    versao = _atualizar_preferencias(crm, v, lead)
    _mover(crm, v, lead, versao, estagio_antes)

    # Encaminhamento entra por aqui, e não pelo nó do grafo, porque só no fim do turno o lead já
    # foi persistido e o estágio anterior ainda é conhecido. No nó, uma falha do CRM abortaria a
    # resposta que o cliente está esperando.
    if lead.estagio == Estagio.HANDOFF and estagio_antes != Estagio.HANDOFF:
        _encaminhar(crm, v, lead)


def _abrir(crm: ClienteCRM, lead: Lead) -> vinculo.Vinculo | None:
    """Cria cliente e oportunidade no CRM na primeira vez que a intenção fica clara.

    Esperar a intenção é deliberado: uma oportunidade precisa de propósito (aluguel ou compra), e
    abrir uma "de compra" para quem só disse "oi" encheria o funil do corretor de intenção
    inventada.
    """
    proposito = traducao.proposito(lead)
    if proposito is None:
        return None

    dados = traducao.identificadores(lead)
    r = crm.chamar("POST", "/v1/leads", corpo=dados,
                   operation_id=_op(lead.id, "lead", dados["external_contact_id"]))
    if not r.ok:
        log.info("CRM não criou o cliente do lead %s: %s", lead.id, r.codigo)
        return None
    crm_lead_id = r.dados["id"]

    r = crm.chamar("POST", "/v1/opportunities",
                   corpo={"lead_id": crm_lead_id, "purpose": proposito},
                   operation_id=_op(lead.id, "oportunidade", proposito))
    if not r.ok:
        log.info("CRM não criou a oportunidade do lead %s: %s", lead.id, r.codigo)
        return None
    return vinculo.salvar(lead.id, crm_lead_id, r.dados["id"], r.dados["version"])


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


def _registrar_conversa(crm: ClienteCRM, v: vinculo.Vinculo, lead: Lead,
                        entrada: MensagemNormalizada, texto_saida: str | None,
                        id_entrada: int | None = None, id_saida: int | None = None) -> None:
    """Uma interação para o que entrou e outra para o que saiu.

    O `external_event_id` é o que impede duplicata quando o mesmo turno é republicado: o CRM
    devolve o registro original em vez de criar uma segunda linha no histórico do cliente.
    """
    quando = datetime.now(UTC).isoformat()

    if entrada.conteudo:
        evento = _evento(lead.id, "in", id_entrada, entrada.conteudo)
        crm.chamar("POST", f"/v1/leads/{v.crm_lead_id}/interactions",
                   corpo={"opportunity_id": v.crm_opportunity_id,
                          "channel": str(entrada.canal.value), "direction": "inbound",
                          "summary": entrada.conteudo[:4000], "occurred_at": quando,
                          "external_event_id": evento},
                   operation_id=_op(lead.id, "interacao-in", evento))
    if texto_saida:
        evento = _evento(lead.id, "out", id_saida, texto_saida)
        crm.chamar("POST", f"/v1/leads/{v.crm_lead_id}/interactions",
                   corpo={"opportunity_id": v.crm_opportunity_id,
                          "channel": str(entrada.canal.value), "direction": "outbound",
                          "summary": texto_saida[:4000], "occurred_at": quando,
                          "external_event_id": evento},
                   operation_id=_op(lead.id, "interacao-out", evento))


def _atualizar_preferencias(crm: ClienteCRM, v: vinculo.Vinculo, lead: Lead) -> int:
    """Devolve a versão atual da oportunidade — que é a precondição do próximo passo.

    Em 412 (alguém editou pelo painel no meio do caminho) relê a oportunidade e tenta uma vez. Isso
    é convivência normal com um corretor trabalhando, não recuperação de erro: por isso UMA
    retentativa, e não um laço.
    """
    corpo = traducao.preferencias(lead)
    marca = hashlib.sha256(repr(sorted(corpo.items())).encode()).hexdigest()[:16]
    r = crm.chamar("PUT", f"/v1/opportunities/{v.crm_opportunity_id}/preferences",
                   corpo=corpo, versao=v.crm_version, operation_id=_op(lead.id, "prefs", marca))

    if r.status == 412:
        atual = crm.chamar("GET", f"/v1/opportunities/{v.crm_opportunity_id}")
        if atual.ok:
            versao = atual.dados["version"]
            vinculo.atualizar_versao(lead.id, versao)
            r = crm.chamar("PUT", f"/v1/opportunities/{v.crm_opportunity_id}/preferences",
                           corpo=corpo, versao=versao, operation_id=_op(lead.id, "prefs", marca))

    if r.ok:
        versao = r.dados.get("opportunity_version", v.crm_version + 1)
        vinculo.atualizar_versao(lead.id, versao)
        return versao
    _registrar_recusa(lead, "preferencias", r)
    return v.crm_version


def _mover(crm: ClienteCRM, v: vinculo.Vinculo, lead: Lead, versao: int,
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
        r = crm.chamar("POST", f"/v1/opportunities/{v.crm_opportunity_id}/transitions",
                       corpo={"target_stage": passo, "reason": None}, versao=versao,
                       operation_id=_op(lead.id, f"estagio-{passo}"))
        if r.ok:
            versao = r.dados["version"]
            vinculo.atualizar_versao(lead.id, versao)
            continue
        if r.codigo == "INVALID_TRANSITION":
            continue        # já estava nesse estágio ou além dele: seguir para o próximo passo
        _registrar_recusa(lead, f"estagio {passo}", r)
        return


def _encaminhar(crm: ClienteCRM, v: vinculo.Vinculo, lead: Lead) -> None:
    """O resumo é o que o corretor lê antes de ligar. Usamos o que a Mora já escreveu; sem resumo
    ainda, o cartão de qualificação é a melhor descrição disponível — bem melhor que 'sem resumo'."""
    c = lead.cartao
    resumo = lead.resumo or "; ".join(
        x for x in [f"intenção: {c.intencao}", c.regiao and f"região: {c.regiao}",
                    c.bairros and f"bairros: {', '.join(str(b) for b in c.bairros)}",
                    c.preco_max and f"até R$ {c.preco_max:,.0f}".replace(",", "."),
                    c.quartos and f"{c.quartos} quarto(s)", c.urgencia and f"urgência: {c.urgencia}"]
        if x)
    r = crm.chamar("POST", "/v1/handoffs",
                   corpo={"opportunity_id": v.crm_opportunity_id,
                          "reason": f"lead {lead.temperatura} encaminhado pela Mora",
                          "summary": resumo[:4000] or "Cliente pediu falar com uma pessoa."},
                   operation_id=_op(lead.id, "handoff"))
    if not r.ok:
        _registrar_recusa(lead, "encaminhamento", r)


def publicar_encaminhamento(lead: Lead, motivo: str, resumo: str) -> None:
    """Passa o atendimento ao corretor NO CRM quando a Mora encaminha.

    Sem isto, o corretor veria no CRM uma oportunidade que o agente ainda conduz, enquanto na
    verdade a conversa já está com ele — e a ficha diria a coisa errada exatamente no momento em
    que alguém vai agir sobre ela.
    """
    if not habilitado():
        return
    try:
        v = vinculo.buscar(lead.id)
        if v is None:
            return
        crm = ClienteCRM()
        r = crm.chamar("POST", "/v1/handoffs",
                       corpo={"opportunity_id": v.crm_opportunity_id,
                              "reason": motivo[:300],
                              "summary": (resumo or motivo)[:4000]},
                       operation_id=_op(lead.id, "handoff"))
        if not r.ok:
            _registrar_recusa(lead, "encaminhamento", r)
    except Exception:
        log.warning("falha ao encaminhar o lead %s no CRM", lead.id, exc_info=True)


def _registrar_recusa(lead: Lead, o_que: str, r) -> None:
    nivel = log.debug if r.codigo in ESPERADOS else log.info
    nivel("CRM recusou %s do lead %s: %s %s", o_que, lead.id, r.codigo, r.mensagem)
