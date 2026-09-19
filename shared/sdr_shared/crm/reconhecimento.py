"""Reconhecer no CRM um cliente que já existe — e começar do que já se sabe sobre ele.

É a parte da integração que muda o atendimento, e não só o registro. Sem isto, um cliente que
falou com um corretor na semana passada recomeça do zero: a Mora pergunta de novo a cidade, o
orçamento e quantos quartos, dados que já estão no CRM, escritos por uma pessoa. Perguntar de novo
o que o cliente já respondeu é a forma mais rápida de um atendimento automático parecer automático.

Três cuidados que o código carrega:

1. **Identificar por contato, nunca por nome.** Nome serve para procurar; duas pessoas podem se
   chamar igual, e confundir uma com a outra entrega o histórico de alguém a um estranho. Se a
   busca devolve mais de um cliente, a Mora segue sem reconhecer — perguntar de novo é chato,
   contar a vida de outra pessoa é grave.

2. **O que o cliente disse agora vale mais que o registro.** O cartão do CRM só preenche campo
   VAZIO. Quem acabou de dizer "agora quero alugar" não é sobrescrito por uma oportunidade de
   compra de seis meses atrás.

3. **Procurar uma vez por contato.** Cliente que o CRM não conhece custaria uma busca por turno,
   para sempre. A marca guardada é derivada do e-mail e do telefone usados: quando o cliente
   informa um contato novo — o caso do chat anônimo do site, onde o e-mail só aparece no meio da
   conversa — a marca muda e vale procurar outra vez.
"""
import hashlib
import logging

from ..db.connection import get_pool
from ..models import Lead
from ..ports import get_crm
from . import traducao, vinculo

log = logging.getLogger("crm.reconhecimento")


def _marca(lead: Lead) -> str:
    """Identidade do contato usado na busca. Muda quando o cliente informa e-mail ou telefone novo."""
    email = (lead.email or lead.cartao.email_informado or "").strip().lower()
    telefone = (lead.telefone or lead.cartao.telefone_informado or "").strip()
    return hashlib.sha256(f"{email}|{telefone}".encode()).hexdigest()[:32]


def _ja_procurado(lead_id: str, marca: str) -> bool:
    with get_pool().connection() as conn:
        linha = conn.execute("SELECT marca_contato FROM crm_reconhecimento WHERE lead_id = %s",
                             (lead_id,)).fetchone()
    return bool(linha) and linha["marca_contato"] == marca


def _anotar(lead_id: str, marca: str, achado: bool) -> None:
    with get_pool().connection() as conn:
        conn.execute(
            """INSERT INTO crm_reconhecimento (lead_id, marca_contato, achado)
               VALUES (%s, %s, %s)
               ON CONFLICT (lead_id) DO UPDATE SET marca_contato = EXCLUDED.marca_contato,
                   achado = EXCLUDED.achado, procurado_em = now()""",
            (lead_id, marca, achado))


def _oportunidade_aberta(lead_do_crm: dict) -> str | None:
    """A oportunidade que ainda está em jogo. Fechada não é contexto: as preferências de uma compra
    concluída conduziriam a conversa nova pela intenção velha."""
    abertas = [o for o in (lead_do_crm.get("opportunities") or [])
               if o.get("stage") in traducao.ABERTAS]
    if not abertas:
        return None
    return str(abertas[-1]["id"])       # a mais recente; a listagem vem em ordem de criação


def reconhecer(lead: Lead) -> bool:
    """Procura o lead no CRM e, se achar, semeia o cartão e cria o vínculo.

    Devolve se o cartão mudou. Nunca levanta: falhar em reconhecer é atender do zero, que é o que
    aconteceria sem CRM nenhum — nunca é motivo para não responder ao cliente.
    """
    try:
        return _reconhecer(lead)
    except Exception:
        log.warning("falha ao reconhecer o lead %s no CRM — segue o atendimento normal", lead.id,
                    exc_info=True)
        return False


def _reconhecer(lead: Lead) -> bool:
    crm = get_crm()
    if not crm.habilitado() or vinculo.buscar(lead.id) is not None:
        return False

    email = lead.email or lead.cartao.email_informado
    telefone = lead.telefone or lead.cartao.telefone_informado
    if not (email or telefone):
        return False            # chat anônimo: não há por onde procurar, e nome não identifica

    marca = _marca(lead)
    if _ja_procurado(lead.id, marca):
        return False

    with crm.sessao() as s:
        achado = s.buscar_lead_por_contato(email=email, telefone=telefone)
        if not achado:
            _anotar(lead.id, marca, achado=False)
            return False

        crm_lead_id = str(achado["id"])
        detalhe = s.consultar_lead(crm_lead_id)
        oportunidade_id = _oportunidade_aberta(detalhe or {})
        if not oportunidade_id:
            # Cliente conhecido, sem oportunidade em aberto: vale o vínculo (o histórico vai para a
            # ficha certa) mas não há preferências a herdar.
            _anotar(lead.id, marca, achado=True)
            return False

        oportunidade = s.consultar_oportunidade(oportunidade_id)
        if not oportunidade:
            _anotar(lead.id, marca, achado=True)
            return False

    mudou = _semear(lead, oportunidade)
    vinculo.salvar(lead.id, crm_lead_id, oportunidade_id,
                   int(oportunidade.get("version", 1)))
    _anotar(lead.id, marca, achado=True)
    log.info("lead %s reconhecido no CRM (%s); cartão %s", lead.id, crm_lead_id,
             "semeado" if mudou else "já estava mais completo")
    return mudou


def _semear(lead: Lead, oportunidade: dict) -> bool:
    """Preenche no cartão só o que está vazio. O que o cliente disse agora tem precedência."""
    do_crm = traducao.cartao_do_crm(oportunidade)
    mudou = False
    for campo, valor in do_crm.items():
        atual = getattr(lead.cartao, campo, None)
        vazio = atual in (None, [], "") or (
            campo == "intencao" and getattr(atual, "value", atual) == "indefinida")
        if vazio:
            setattr(lead.cartao, campo, valor)
            mudou = True
    return mudou
