"""Consistência de dados com o pool em autocommit: transações de verdade e contato disputado.

As falhas são injetadas com um gatilho do Postgres que levanta exceção na ÚLTIMA instrução de cada
operação. Com autocommit, tudo o que veio antes já estava gravado quando ela falhava — o teste
confere que, com a transação, nada fica pela metade.
"""
import os
import threading
import uuid
from contextlib import contextmanager

import pytest

os.environ.setdefault("SDR_DATABASE_DSN", "postgresql://sdr:sdr@localhost:5433/sdr_test")
from sdr_shared.db.guarda_teste import exigir_banco_de_teste; exigir_banco_de_teste()   # noqa: E702

from sdr_shared.db import (CanalRepository, ClienteRepository, CorretorRepository, LeadRepository,
                           get_pool, nova_oportunidade_se_mudou_intencao)
from sdr_shared.models import CartaoQualificacao, Corretor, Estagio, Intencao, Lead


def _sql(q: str, p: tuple = ()):
    with get_pool().connection() as c:
        return c.execute(q, p)


@contextmanager
def falha_em(tabela: str, quando: str = "true"):
    """Faz o próximo UPDATE em `tabela` (que satisfaça `quando`) levantar exceção."""
    _sql("""CREATE OR REPLACE FUNCTION falha_injetada() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'falha injetada pelo teste'; END $$ LANGUAGE plpgsql""")
    _sql(f"""CREATE TRIGGER falha_injetada BEFORE UPDATE ON {tabela}
             FOR EACH ROW WHEN ({quando}) EXECUTE FUNCTION falha_injetada()""")
    try:
        yield
    finally:
        _sql(f"DROP TRIGGER IF EXISTS falha_injetada ON {tabela}")


def _sufixo() -> str:
    return uuid.uuid4().hex[:8]


# ------------------------------------------------------------------ B5: transações

def test_desativar_corretor_e_tudo_ou_nada():
    """O comentário já prometia "tudo numa transação só"; com autocommit eram quatro commits.
    Falhando o último (desligar o corretor), a carteira já tinha ido para outro e ele seguia ativo."""
    s = _sufixo()
    repo = CorretorRepository()
    repo.upsert(Corretor(id=f"cor_a{s}", nome="A", ativo=True))
    repo.upsert(Corretor(id=f"cor_b{s}", nome="B", ativo=True))
    LeadRepository().upsert(Lead(id=f"l{s}", nome="X", corretor_id=f"cor_a{s}"))

    with falha_em("corretores"), pytest.raises(Exception, match="falha injetada"):
        repo.desativar(f"cor_a{s}", f"cor_b{s}")

    assert LeadRepository().get(f"l{s}").corretor_id == f"cor_a{s}", "metade da carteira movida"
    assert repo.get(f"cor_a{s}").ativo is True


def test_atribuir_corretor_move_lead_e_visitas_juntos():
    s = _sufixo()
    CorretorRepository().upsert(Corretor(id=f"cor_a{s}", nome="A", ativo=True))
    CorretorRepository().upsert(Corretor(id=f"cor_b{s}", nome="B", ativo=True))
    LeadRepository().upsert(Lead(id=f"l{s}", nome="X", corretor_id=f"cor_a{s}"))
    _sql("""INSERT INTO visitas (id, lead_id, tipo, inicio, corretor_id)
            VALUES (%s, %s, 'visita', now() + interval '3 days' + %s * interval '1 minute', %s)""",
         (f"v{s}", f"l{s}", int(s, 16) % 50000, f"cor_a{s}"))

    with falha_em("visitas"), pytest.raises(Exception, match="falha injetada"):
        LeadRepository().atribuir_corretor(f"l{s}", f"cor_b{s}")

    assert LeadRepository().get(f"l{s}").corretor_id == f"cor_a{s}", \
        "lead com um corretor e a visita dele com outro"


def test_sucessao_de_oportunidade_e_tudo_ou_nada():
    """Abrir a nova, mover o canal e encerrar a antiga eram três commits. Falhando o último, o
    cliente ficava com DUAS oportunidades abertas e o canal já entregando na nova."""
    s = _sufixo()
    lead = LeadRepository().upsert(Lead(id=f"l{s}", nome="X", estagio=Estagio.HANDOFF,
                                        cartao=CartaoQualificacao(intencao=Intencao.COMPRA)))
    CanalRepository().vincular(lead.id, "telegram", f"chat{s}")

    with falha_em("leads", "NEW.encerrado_em IS NOT NULL"), pytest.raises(Exception, match="falha injetada"):
        nova_oportunidade_se_mudou_intencao(lead, Intencao.ALUGUEL)

    assert LeadRepository().get_por_canal("telegram", f"chat{s}").id == lead.id
    abertas = _sql("SELECT count(*) AS n FROM leads WHERE nome = 'X' AND sucessora_id IS NULL "
                   "AND id LIKE 'opo_%%' AND criado_em > now() - interval '5 seconds'").fetchone()["n"]
    assert abertas == 0, "oportunidade nova ficou órfã"
    assert LeadRepository().get(lead.id).encerrado_em is None


def test_sucessao_sem_falha_continua_funcionando():
    s = _sufixo()
    lead = LeadRepository().upsert(Lead(id=f"l{s}", nome="Y", estagio=Estagio.HANDOFF,
                                        cartao=CartaoQualificacao(intencao=Intencao.COMPRA)))
    CanalRepository().vincular(lead.id, "telegram", f"chat{s}")
    nova = nova_oportunidade_se_mudou_intencao(lead, Intencao.ALUGUEL)
    assert nova is not None
    assert LeadRepository().get_por_canal("telegram", f"chat{s}").id == nova.id
    assert LeadRepository().get(lead.id).sucessora_id == nova.id


# ------------------------------------------------------------------ B7: contato disputado

def test_telefone_de_um_cliente_e_email_de_outro_nao_derruba_o_turno():
    """Telefone do cliente A, e-mail do cliente B: o COALESCE tentava gravar o e-mail de B em A e
    violava o índice único — o turno do agente inteiro caía."""
    s = _sufixo()
    tel_a, mail_b = f"1199{int(s, 16) % 10**7:07d}", f"b{s}@exemplo.com"
    a = ClienteRepository().vincular(Lead(id=f"la{s}", telefone=tel_a))
    b = ClienteRepository().vincular(Lead(id=f"lb{s}", email=mail_b))
    LeadRepository().upsert(Lead(id=f"lc{s}"))

    cliente = ClienteRepository().vincular(Lead(id=f"lc{s}", telefone=tel_a, email=mail_b))

    assert cliente == a, "o telefone manda"
    assert ClienteRepository().get(a).email is None, "o e-mail é de B, não pode ir para A"
    assert ClienteRepository().get(b).email == mail_b
    conflito = _sql("""SELECT dados FROM auditoria WHERE acao = 'cliente.contato_em_conflito'
                        AND entidade_id = %s""", (a,)).fetchone()
    assert conflito is not None and conflito["dados"]["email_de"] == b


def test_dois_leads_com_o_mesmo_telefone_novo_ao_mesmo_tempo():
    """Os dois procuram, não acham, e criam. O segundo INSERT violava o índice de telefone."""
    s = _sufixo()
    tel = f"1198{int(s, 16) % 10**7:07d}"
    ids = [f"l1{s}", f"l2{s}"]
    for i in ids:
        LeadRepository().upsert(Lead(id=i))

    barreira, resultado, erros = threading.Barrier(2), {}, []
    original, local = ClienteRepository.por_contato, threading.local()

    def por_contato_sincronizado(self, *a, **k):
        r = original(self, *a, **k)
        if not getattr(local, "esperou", False):
            local.esperou = True
            barreira.wait(timeout=5)           # os dois leram "não existe" antes de qualquer INSERT
        return r

    def rodar(lead_id):
        try:
            resultado[lead_id] = ClienteRepository().vincular(Lead(id=lead_id, telefone=tel))
        except Exception as e:                  # pragma: no cover - é o defeito
            erros.append(e)

    ClienteRepository.por_contato = por_contato_sincronizado
    try:
        ts = [threading.Thread(target=rodar, args=(i,)) for i in ids]
        [t.start() for t in ts]
        [t.join(10) for t in ts]
    finally:
        ClienteRepository.por_contato = original
    assert not erros, erros
    assert resultado[ids[0]] == resultado[ids[1]], "a mesma pessoa virou dois clientes"
    assert _sql("SELECT count(*) AS n FROM clientes WHERE telefone = %s", (tel,)).fetchone()["n"] == 1


def test_desativar_com_destino_ocupado_no_mesmo_horario_nao_estoura():
    """Com o índice único de horário por corretor, mover para o destino uma visita no horário em
    que ele já tem outra estourava o UPDATE inteiro. A que colide vai para a fila da equipe e volta
    em `visitas_em_conflito`; o resto da carteira segue para o destino."""
    s = _sufixo()
    repo = CorretorRepository()
    repo.upsert(Corretor(id=f"cor_a{s}", nome="A", ativo=True))
    repo.upsert(Corretor(id=f"cor_b{s}", nome="B", ativo=True))
    for i in ("1", "2", "3"):
        LeadRepository().upsert(Lead(id=f"l{i}{s}"))
    minuto = int(s, 16) % 50000
    for vid, lead, corretor, extra in ((f"va{s}", f"l1{s}", f"cor_a{s}", 0), (f"vb{s}", f"l2{s}", f"cor_b{s}", 0),
                                       (f"va2{s}", f"l3{s}", f"cor_a{s}", 90)):
        _sql("""INSERT INTO visitas (id, lead_id, tipo, inicio, corretor_id)
                VALUES (%s, %s, 'visita', date_trunc('minute', now()) + interval '30 days'
                                          + %s * interval '1 minute', %s)""",
             (vid, lead, minuto + extra, corretor))

    movido = repo.desativar(f"cor_a{s}", f"cor_b{s}")

    assert movido["visitas"] == 1 and movido["visitas_em_conflito"] == [f"va{s}"]
    donos = {r["id"]: r["corretor_id"] for r in _sql(
        "SELECT id, corretor_id FROM visitas WHERE id IN (%s, %s, %s)", (f"va{s}", f"vb{s}", f"va2{s}")).fetchall()}
    assert donos == {f"va{s}": None, f"vb{s}": f"cor_b{s}", f"va2{s}": f"cor_b{s}"}
    _sql("DELETE FROM visitas WHERE id IN (%s, %s, %s)", (f"va{s}", f"vb{s}", f"va2{s}"))
