"""Cliente é a pessoa; lead é a oportunidade. O corretor não pode perder o histórico de quem já atendeu."""
import os
os.environ.setdefault("SDR_DATABASE_DSN", "postgresql://sdr:sdr@localhost:5433/sdr_test")
from sdr_shared.db.guarda_teste import exigir_banco_de_teste; exigir_banco_de_teste()
os.environ["SDR_PROFILE"] = "local"
from sdr_shared.db import ClienteRepository, LeadRepository, get_pool, nova_oportunidade_se_mudou_intencao
from sdr_shared.models import CartaoQualificacao, Estagio, Intencao, Lead


def setup_function(_):
    with get_pool().connection() as c:
        for t in ("visitas", "mensagens", "canais", "followups_agendados", "eventos_navegacao", "auditoria", "leads", "clientes"):
            c.execute(f"DELETE FROM {t}")


def _lead(id, **kw) -> Lead:
    return LeadRepository().upsert(Lead(id=id, **kw))


def test_sem_contato_nao_inventamos_um_cliente():
    lead = _lead("web_anon")
    assert ClienteRepository().vincular(lead) is None, "duas sessões anônimas não são a mesma pessoa"


def test_mesmo_telefone_no_telegram_e_na_web_e_um_cliente_so():
    repo = ClienteRepository()
    whats = _lead("wa_1", nome="Marcos", telefone="11988887777")
    web = _lead("web_2", telefone="(11) 98888-7777")          # o cliente digitou formatado
    primeiro = repo.vincular(whats)
    segundo = repo.vincular(web)
    assert primeiro == segundo
    assert len(repo.oportunidades(primeiro)) == 2
    assert repo.get(primeiro).nome == "Marcos"                 # o nome veio da conversa que o tinha


def test_email_tambem_reconhece_e_o_cadastro_se_completa():
    repo = ClienteRepository()
    a = _lead("web_1", email="Marcos@Exemplo.com")
    cid = repo.vincular(a)
    b = _lead("web_2", email="marcos@exemplo.com", telefone="11955554444")
    assert repo.vincular(b) == cid                              # caixa alta não cria outra pessoa
    assert repo.get(cid).telefone == "11955554444"              # e o telefone novo enriquece a ficha


def test_intencao_nova_depois_do_ciclo_abre_outra_oportunidade():
    lead = _lead("wa_1", telefone="11988887777", estagio=Estagio.HANDOFF,
                 cartao=CartaoQualificacao(intencao=Intencao.COMPRA, regiao="zona_sul", quartos=3))
    ClienteRepository().vincular(lead)
    nova = nova_oportunidade_se_mudou_intencao(lead, Intencao.ALUGUEL)
    assert nova is not None and nova.id != lead.id
    assert nova.cliente_id == lead.cliente_id and nova.telefone == "11988887777"
    assert nova.cartao.quartos is None, "o que ela procura recomeça; o contato é que segue"

    antiga = LeadRepository().get(lead.id)
    assert antiga.encerrado_em and antiga.sucessora_id == nova.id
    assert antiga.cartao.intencao == Intencao.COMPRA, "a oportunidade anterior guarda o que era"
    assert [l.id for l in LeadRepository().listar()] == [nova.id], "a fila do corretor só mostra o que está aberto"


def test_correcao_no_meio_da_qualificacao_nao_abre_oportunidade():
    lead = _lead("web_1", estagio=Estagio.QUALIFICANDO, cartao=CartaoQualificacao(intencao=Intencao.COMPRA))
    assert nova_oportunidade_se_mudou_intencao(lead, Intencao.ALUGUEL) is None, "aqui o cliente só se corrigiu"


def test_primeira_intencao_declarada_nao_abre_oportunidade():
    lead = _lead("wa_1", estagio=Estagio.FRIO, cartao=CartaoQualificacao(intencao=Intencao.INDEFINIDA))
    assert nova_oportunidade_se_mudou_intencao(lead, Intencao.COMPRA) is None


def test_ficha_reune_o_historico_da_pessoa():
    repo = ClienteRepository()
    a = _lead("wa_1", nome="Marcos", telefone="11988887777",
              cartao=CartaoQualificacao(intencao=Intencao.COMPRA))
    cid = repo.vincular(a)
    b = _lead("web_2", telefone="11988887777", cliente_id=cid,
              cartao=CartaoQualificacao(intencao=Intencao.ALUGUEL))
    repo.vincular(b)
    ficha = repo.ficha(cid)
    assert ficha["total_oportunidades"] == 2
    assert ficha["intencoes"] == ["aluguel", "compra"]
    assert ficha["cliente"]["nome"] == "Marcos"
