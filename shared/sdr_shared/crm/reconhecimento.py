"""Reconhecer no CRM um cliente que já existe — e começar do que já se sabe sobre ele.

É a parte da integração que muda o atendimento, e não só o registro. Sem isto, um cliente que
falou com um corretor na semana passada recomeça do zero: a Mora pergunta de novo a cidade, o
orçamento e quantos quartos, dados que já estão no CRM, escritos por uma pessoa. Perguntar de novo
o que o cliente já respondeu é a forma mais rápida de um atendimento automático parecer automático.

**Contato autodeclarado não reconhece (S4).** Telefone e e-mail digitados no chat não provam
quem está do outro lado. Um visitante anônimo que informava o contato de um cliente existente era
vinculado à oportunidade aberta dele: herdava orçamento e bairros (que a Mora então repetia para
ele) e tudo o que escrevesse entrava na ficha da vítima. Agora a coincidência é só SINALIZADA —
auditoria `cliente.contato_coincide`, aviso no painel e, quando o lead nasce no CRM, uma observação
interna na ficha NOVA — e o corretor decide se é a mesma pessoa. Semear e vincular continuam
existindo para contato verificado pelo canal (`contato_verificado=True`); hoje nenhum canal entrega
um (o Telegram identifica o chat, não o telefone, e a continuidade dele já vem do próprio vínculo).

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


def reconhecer(lead: Lead, *, contato_verificado: bool = False) -> bool:
    """Procura o lead no CRM. Com contato verificado, semeia o cartão e cria o vínculo; com contato
    autodeclarado (o caso de todo canal hoje), só sinaliza a coincidência.

    Devolve se o cartão mudou. Nunca levanta: falhar em reconhecer é atender do zero, que é o que
    aconteceria sem CRM nenhum — nunca é motivo para não responder ao cliente.
    """
    try:
        return _reconhecer(lead, contato_verificado)
    except Exception:
        log.warning("falha ao reconhecer o lead %s no CRM — segue o atendimento normal", lead.id,
                    exc_info=True)
        return False


def _contato(lead: Lead) -> tuple[str | None, str | None]:
    return (lead.email or lead.cartao.email_informado, lead.telefone or lead.cartao.telefone_informado)


def _reconhecer(lead: Lead, contato_verificado: bool) -> bool:
    crm = get_crm()
    if not crm.habilitado() or vinculo.buscar(lead.id) is not None:
        return False

    email, telefone = _contato(lead)
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
        if not contato_verificado:
            _sinalizar(lead, crm_lead_id)
            _anotar(lead.id, marca, achado=True)
            return False

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


def _sinalizar(lead: Lead, crm_lead_id: str) -> None:
    """Deixa a coincidência à vista do corretor, sem decidir por ele. Chamado uma vez por contato
    (quem chama confere a marca antes)."""
    from ..db import auditar, notificar
    auditar(acao="cliente.contato_coincide", entidade="lead", entidade_id=lead.id,
            ator_tipo="agente", ator_nome="Mora", origem="crm",
            dados={"crm_lead_id": crm_lead_id},
            detalhe="contato informado no chat coincide com cliente já cadastrado no CRM; "
                    "não vinculado — confirmar identidade antes de juntar as fichas")
    notificar(tipo="cliente.contato_coincide", corretor_id=lead.corretor_id, lead_id=lead.id,
              titulo="Contato informado coincide com cliente do CRM",
              detalhe="O lead segue como novo. Confirme com a pessoa antes de juntar as fichas.",
              dados={"crm_lead_id": crm_lead_id}, chave=_marca(lead))
    log.info("lead %s informou contato de um cliente do CRM (%s); não vinculado", lead.id, crm_lead_id)


def contato_coincidente(s, lead: Lead) -> str | None:
    """Para a publicação, ANTES de criar o lead no CRM: o contato autodeclarado casa com um cliente
    que já existe? Devolve o id dele.

    Necessário porque `criar_lead` deduplica por e-mail e telefone e devolveria a ficha da vítima —
    e o contato pode ter aparecido no mesmo turno em que a intenção ficou clara, antes de qualquer
    `reconhecer()`. Sinaliza se ainda não tiver sinalizado para este contato."""
    email, telefone = _contato(lead)
    if not (email or telefone):
        return None
    achado = s.buscar_lead_por_contato(email=email, telefone=telefone)
    if not achado:
        return None
    marca = _marca(lead)
    if not _ja_procurado(lead.id, marca):
        _sinalizar(lead, str(achado["id"]))
        _anotar(lead.id, marca, achado=True)
    return str(achado["id"])


def sem_contato(lead: Lead) -> Lead:
    """Cópia do lead sem e-mail e telefone, para abrir no CRM uma ficha que não seja deduplicada
    com a de outra pessoa. O `external_contact_id` (`mora-<id>`) continua identificando."""
    cartao = lead.cartao.model_copy(update={"email_informado": None, "telefone_informado": None})
    return lead.model_copy(update={"email": None, "telefone": None, "cartao": cartao})


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
