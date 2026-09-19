"""Cliente = a pessoa; Lead = a oportunidade dela.

Duas coisas acontecem aqui, e as duas existem para o corretor não perder contexto:
  1. Deduplicação — o visitante anônimo da web que informa o telefone é a mesma pessoa que já falou
     com a gente pelo Telegram no mês passado. Assim que há um contato, os dois viram um cliente só.
  2. Nova oportunidade — quem comprou ano passado e volta querendo alugar não é a mesma negociação.
     A oportunidade anterior é encerrada (não apagada) e uma nova começa, ligada ao mesmo cliente.
"""
import uuid
from datetime import datetime, timezone

from ..models import Cliente, Estagio, Intencao, Lead
from .connection import get_pool

COLS = "id, nome, telefone, email, criado_em, atualizado_em"

# Estágios em que a oportunidade já cumpriu (ou perdeu) seu ciclo. Mudar de intenção aqui abre outra;
# mudar de intenção no meio da qualificação é o cliente se corrigindo, e só ajusta o cartão.
ENCERRAVEIS = {Estagio.AGENDADO, Estagio.HANDOFF, Estagio.INATIVO, Estagio.FRIO}


def _conn():
    return get_pool().connection()


def _so_digitos(telefone: str | None) -> str | None:
    if not telefone:
        return None
    d = "".join(ch for ch in telefone if ch.isdigit())
    return d or None


class ClienteRepository:
    def get(self, cliente_id: str) -> Cliente | None:
        with _conn() as c:
            r = c.execute(f"SELECT {COLS} FROM clientes WHERE id = %s", (cliente_id,)).fetchone()
        return Cliente(**dict(r)) if r else None

    def por_contato(self, telefone: str | None = None, email: str | None = None) -> Cliente | None:
        """O telefone manda: é o identificador que o corretor usa. O e-mail é o segundo caminho."""
        tel, mail = _so_digitos(telefone), (email or "").strip().lower() or None
        if not tel and not mail:
            return None
        with _conn() as c:
            r = c.execute(f"""SELECT {COLS} FROM clientes
                              WHERE (%(tel)s::text IS NOT NULL AND telefone = %(tel)s)
                                 OR (%(mail)s::text IS NOT NULL AND lower(email) = %(mail)s)
                              ORDER BY (telefone = %(tel)s) DESC NULLS LAST, criado_em LIMIT 1""",
                          {"tel": tel, "mail": mail}).fetchone()
        return Cliente(**dict(r)) if r else None

    def vincular(self, lead: Lead) -> str | None:
        """Liga a oportunidade a um cliente — achando o existente pelo contato, ou criando um.

        Sem nenhum contato não dá para afirmar que duas conversas são a mesma pessoa, então não
        inventamos um cliente: a oportunidade segue solta até o contato aparecer.
        """
        if not (lead.telefone or lead.email):
            return lead.cliente_id
        existente = self.por_contato(lead.telefone, lead.email)
        cliente_id = existente.id if existente else f"cli_{uuid.uuid4().hex[:12]}"
        tel, mail = _so_digitos(lead.telefone), (lead.email or "").strip().lower() or None
        with _conn() as c:
            c.execute("""
                INSERT INTO clientes (id, nome, telefone, email)
                VALUES (%(id)s, %(nome)s, %(tel)s, %(mail)s)
                ON CONFLICT (id) DO UPDATE SET
                  nome = COALESCE(clientes.nome, EXCLUDED.nome),
                  telefone = COALESCE(clientes.telefone, EXCLUDED.telefone),
                  email = COALESCE(clientes.email, EXCLUDED.email),
                  atualizado_em = now()""",
                {"id": cliente_id, "nome": lead.nome, "tel": tel, "mail": mail})
            c.execute("UPDATE leads SET cliente_id = %s WHERE id = %s", (cliente_id, lead.id))
        lead.cliente_id = cliente_id
        return cliente_id

    def oportunidades(self, cliente_id: str) -> list[dict]:
        """Histórico completo da pessoa — o que o corretor abre antes de ligar."""
        with _conn() as c:
            rows = c.execute("""
                SELECT l.id, l.estagio, l.temperatura, l.score, l.cartao, l.corretor_id, l.resumo,
                       l.criado_em, l.ultima_mensagem_em, l.encerrado_em, l.sucessora_id,
                       co.nome AS corretor_nome,
                       (SELECT count(*) FROM mensagens m WHERE m.lead_id = l.id) AS mensagens,
                       (SELECT count(*) FROM visitas v WHERE v.lead_id = l.id) AS visitas
                FROM leads l LEFT JOIN corretores co ON co.id = l.corretor_id
                WHERE l.cliente_id = %s ORDER BY l.criado_em DESC""", (cliente_id,)).fetchall()
        return [dict(r) for r in rows]

    def ficha(self, cliente_id: str) -> dict | None:
        cliente = self.get(cliente_id)
        if not cliente:
            return None
        ops = self.oportunidades(cliente_id)
        return {"cliente": cliente.model_dump(mode="json"), "oportunidades": ops,
                "total_oportunidades": len(ops),
                "intencoes": sorted({(o["cartao"] or {}).get("intencao", "indefinida") for o in ops})}

    def listar(self, busca: str | None = None, limite: int = 200) -> list[dict]:
        with _conn() as c:
            rows = c.execute(f"""
                SELECT {', '.join('c.' + x for x in COLS.split(', '))},
                       count(l.id) AS oportunidades,
                       max(l.ultima_mensagem_em) AS ultima_atividade,
                       count(l.id) FILTER (WHERE l.encerrado_em IS NULL) AS abertas
                FROM clientes c LEFT JOIN leads l ON l.cliente_id = c.id
                WHERE (%(q)s::text IS NULL OR c.nome ILIKE %(q)s OR c.telefone ILIKE %(q)s OR c.email ILIKE %(q)s)
                GROUP BY c.id ORDER BY max(l.ultima_mensagem_em) DESC NULLS LAST LIMIT %(lim)s""",
                {"q": f"%{busca}%" if busca else None, "lim": limite}).fetchall()
        return [dict(r) for r in rows]


def nova_oportunidade_se_mudou_intencao(lead: Lead, nova: Intencao) -> Lead | None:
    """Cliente que já fechou um ciclo e volta com outra intenção começa uma oportunidade nova.

    Devolve a nova oportunidade (já persistida) ou None quando é só o cliente se corrigindo no meio
    da qualificação — nesse caso o cartão atual é ajustado e nada mais acontece.
    """
    from .repositories import LeadRepository

    atual = lead.cartao.intencao
    if nova in (Intencao.INDEFINIDA, atual) or atual == Intencao.INDEFINIDA:
        return None
    if lead.estagio not in ENCERRAVEIS or not lead.ativa():
        return None

    repo = LeadRepository()
    nova_id = f"opo_{uuid.uuid4().hex[:12]}"
    sucessora = Lead(
        id=nova_id, cliente_id=lead.cliente_id, nome=lead.nome, telefone=lead.telefone, email=lead.email,
        estagio=Estagio.QUALIFICANDO,
        # o contato e a pessoa seguem; o que ela procura recomeça do zero
        cartao=lead.cartao.model_copy(update={
            "intencao": nova, "regiao": None, "bairros": [], "preco_min": None, "preco_max": None,
            "quartos": None, "tipo_imovel": None, "urgencia": None, "perfil_investidor": None,
            "ticket": None, "retorno_esperado": None, "imoveis_visualizados": [], "pediu_visita": False}),
        corretor_id=lead.corretor_id)
    repo.upsert(sucessora)
    with _conn() as c:
        # o canal do cliente passa a entregar na oportunidade nova; a antiga guarda seu histórico
        c.execute("UPDATE canais SET lead_id = %s WHERE lead_id = %s", (nova_id, lead.id))
    lead.encerrado_em = datetime.now(timezone.utc)
    lead.sucessora_id = nova_id
    repo.encerrar(lead.id, nova_id)
    return sucessora
