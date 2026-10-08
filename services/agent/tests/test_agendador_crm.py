"""Como o agendador usa (e deixa de usar) o CRM.

A verdade da integração — pedido é `requested`, oportunidade não vai para `visit_scheduled` — é
provada contra o CRM real em `shared/tests/test_visitas_crm.py`. Aqui fica só a ligação: de onde
vem a grade de horários, o que sobrevive no estado entre os dois turnos, e o que acontece quando o
CRM não responde. São dublês porque é isso que está sob prova.
"""
from datetime import UTC, datetime, timedelta

import pytest
from sdr_shared.crm import Horario
from sdr_shared.messaging import Canal, MensagemNormalizada, TipoMensagem
from sdr_shared.models import Estagio, ImovelCard, Intencao, Lead

from agent.nodes import agendador


def entrada(texto: str) -> MensagemNormalizada:
    return MensagemNormalizada(lead_id="lead-ag", canal=Canal.WEB, tipo=TipoMensagem.TEXTO,
                               identificador_canal="s", conteudo=texto)


@pytest.fixture
def lead_no_banco():
    """A reserva grava uma visita de verdade no banco da Mora, e visita tem chave estrangeira para
    lead. Sem isto os testes de escolha falham no banco, e não no comportamento."""
    from sdr_shared.db import LeadRepository
    lead = Lead(id="lead-ag", nome="Cliente", estagio=Estagio.QUALIFICADO)
    lead.cartao.intencao = Intencao.ALUGUEL
    return LeadRepository().upsert(lead)


def estado(texto: str, sem_contato: bool = False, **extra) -> dict:
    # Com telefone: é o caminho normal da reserva no site (sem contato, a Mora segura o horário
    # e pede o telefone antes — ver os testes da trava no fim do arquivo).
    lead = Lead(id="lead-ag", nome="Cliente", estagio=Estagio.QUALIFICADO,
                telefone=None if sem_contato else "11988887777")
    lead.cartao.intencao = Intencao.ALUGUEL
    card = ImovelCard(id="SP-0001", titulo="Apartamento 2q · Pinheiros", preco=3000.0,
                      foto=None, motivo="perto do metrô")
    return {"lead": lead, "entrada": entrada(texto), "messages": [], "saltos": 0,
            "imoveis_sugeridos": [card], **extra}


@pytest.fixture
def grade(monkeypatch):
    """Horários do CRM, com `slot_id` — que é o que distingue de uma grade da agenda do corretor."""
    base = (datetime.now(UTC) + timedelta(days=2)).replace(hour=14, minute=0, second=0,
                                                           microsecond=0)
    horarios = [Horario(inicio=base + timedelta(days=i), slot_id=f"slot-{i}") for i in range(3)]
    monkeypatch.setattr(agendador, "horarios_do_imovel", lambda codigo, *a, **k: horarios)
    return horarios


@pytest.fixture
def pedidos(monkeypatch):
    registrados = []
    monkeypatch.setattr(agendador, "pedir_visita",
                        lambda lead, codigo, slot, **k: registrados.append((codigo, slot)) or True)
    return registrados


# --------------------------------------------------------------------------- de onde vem a grade

def test_com_imovel_a_grade_vem_do_crm(infra, grade, monkeypatch):
    """Horário de visita a um imóvel é dado comercial da imobiliária: quem sabe é o CRM."""
    monkeypatch.setattr(agendador, "listar_horarios",
                        lambda **k: pytest.fail("não devia ter usado a agenda do corretor"))
    out = agendador.run(estado("quero visitar"))
    assert out["horarios_oferecidos"] == [h.inicio.isoformat() for h in grade]
    assert out["slots_crm"] == {h.inicio.isoformat(): h.slot_id for h in grade}


def test_sem_resposta_do_crm_cai_na_agenda_do_corretor(infra, monkeypatch):
    """Lista vazia é "não sei", nunca "não há". Recusar visita por falha de integração seria
    inventar indisponibilidade — e o agendamento tem de funcionar sem CRM nenhum."""
    monkeypatch.setattr(agendador, "horarios_do_imovel", lambda *a, **k: [])
    out = agendador.run(estado("quero visitar"))
    assert out["horarios_oferecidos"], "a oferta não pode ficar vazia"
    assert out["slots_crm"] == {}, "sem slot do CRM não há o que pedir depois"


# --------------------------------------------------------------------------- do turno 1 ao turno 2

def test_o_slot_escolhido_vira_o_pedido(infra, grade, pedidos, lead_no_banco):
    """O `slot_id` precisa atravessar os dois turnos: a grade é oferecida num, a escolha vem no
    outro. Sem isso, o pedido nasceria sem horário e o CRM o recusaria."""
    escolhido = grade[1]
    out = agendador.run(estado(f"slot:{escolhido.inicio.isoformat()}",
                               horarios_oferecidos=[h.inicio.isoformat() for h in grade],
                               slots_crm={h.inicio.isoformat(): h.slot_id for h in grade}))
    assert pedidos == [("SP-0001", escolhido.slot_id)]
    assert out["slots_crm"] == {}, "a grade não pode sobrar para o próximo agendamento"


def test_horario_da_agenda_do_corretor_nao_inventa_slot(infra, pedidos, monkeypatch, lead_no_banco):
    """Quando a grade veio do corretor não há `slot_id`. A reserva da Mora vale do mesmo jeito; o
    pedido fica sem onde ser pendurado, e inventar um identificador seria pior que não pedir."""
    monkeypatch.setattr(agendador, "horarios_do_imovel", lambda *a, **k: [])
    quando = (datetime.now(UTC) + timedelta(days=2)).replace(hour=14, minute=0, second=0,
                                                             microsecond=0)
    agendador.run(estado(f"slot:{quando.isoformat()}",
                         horarios_oferecidos=[quando.isoformat()], slots_crm={}))
    assert pedidos == [("SP-0001", None)]


def test_falha_do_pedido_nao_desfaz_a_reserva(infra, grade, monkeypatch, lead_no_banco):
    """O cliente tem o horário e o corretor recebe a notificação da Mora de qualquer jeito. O que
    se perde é o pedido aparecer no painel do CRM — ruim, e muito menos ruim que derrubar o
    atendimento por causa disso."""
    def recusar(*a, **k):
        return False
    monkeypatch.setattr(agendador, "pedir_visita", recusar)
    escolhido = grade[0]
    out = agendador.run(estado(f"slot:{escolhido.inicio.isoformat()}",
                               horarios_oferecidos=[h.inicio.isoformat() for h in grade],
                               slots_crm={h.inicio.isoformat(): h.slot_id for h in grade}))
    assert out["resposta"].texto
    assert out["lead"].estagio == Estagio.AGENDADO


def test_erro_do_crm_nao_derruba_o_turno(infra, grade, monkeypatch, lead_no_banco):
    def explodir(*a, **k):
        raise RuntimeError("CRM caiu no meio")
    monkeypatch.setattr(agendador, "pedir_visita", explodir)
    escolhido = grade[0]
    with pytest.raises(RuntimeError):
        # O módulo de visitas engole a própria falha; aqui o dublê levanta de propósito para
        # documentar que o nó NÃO tem try próprio — a garantia mora em `sdr_shared.crm.visitas`,
        # e este teste existe para que mover essa responsabilidade não passe despercebido.
        agendador.run(estado(f"slot:{escolhido.inicio.isoformat()}",
                             horarios_oferecidos=[h.inicio.isoformat() for h in grade],
                             slots_crm={h.inicio.isoformat(): h.slot_id for h in grade}))


# --------------------------------------------------------------- o prompt da confirmação

def _prompt_capturado(monkeypatch) -> list[str]:
    """Captura o prompt de sistema que o agendador manda ao modelo."""
    capturado: list[str] = []
    from langchain_core.messages import AIMessage

    class Espiao:
        def invoke(self, msgs):
            capturado.append(msgs[0].content)
            return AIMessage(content="[resposta da Mora]")

    monkeypatch.setattr(agendador, "llm_conversa", lambda: Espiao())
    return capturado


def test_confirmacao_nao_deixa_placeholder_no_prompt(monkeypatch, lead_no_banco, grade):
    """O defeito que o cliente viu: a Mora confirmou a visita E disse, na mesma resposta, que o
    horário não estava disponível, reoferecendo a lista.

    A causa está aqui. O ramo da confirmação chamava `carregar("agendador", ...)` sem passar
    `pedido_invalido`, e `_fmt` substitui chave faltante por ela mesma — então o modelo recebia,
    literalmente, "Se {pedido_invalido} for verdadeiro, o cliente pediu um horário que não existe".
    Sobrava ao modelo adivinhar, e às vezes ele adivinhava que sim.

    Placeholder não resolvido em prompt não é cosmético: é uma instrução que o modelo lê e obedece.
    """
    capturado = _prompt_capturado(monkeypatch)
    slots = [h.inicio for h in grade]
    agendador.run(estado(f"slot:{slots[0].isoformat()}",
                         horarios_oferecidos=[s.isoformat() for s in slots]))
    assert capturado, "o agendador não chegou a chamar o modelo"
    import re
    sobrando = re.findall(r"\{[A-Za-z_][A-Za-z0-9_]*\}", capturado[0])
    assert not sobrando, f"placeholders não resolvidos chegaram ao modelo: {sobrando}"


def test_confirmacao_nao_manda_a_lista_de_horarios(monkeypatch, lead_no_banco, grade):
    """Confirmando, não há o que oferecer. A lista no prompt é o que alimenta um 'temos também às
    10h, 14h ou 16h' colado à confirmação."""
    capturado = _prompt_capturado(monkeypatch)
    slots = [h.inicio for h in grade]
    agendador.run(estado(f"slot:{slots[0].isoformat()}",
                         horarios_oferecidos=[s.isoformat() for s in slots]))
    corpo = capturado[0]
    assert agendador.formatar(slots[0]) in corpo, "o horário reservado precisa estar no prompt"
    outros = [agendador.formatar(s) for s in slots[1:]]
    assert not [o for o in outros if o in corpo], "a confirmação não deve carregar os outros horários"


def test_clique_no_botao_nao_vira_iso_no_historico(monkeypatch, lead_no_banco, grade):
    """`slot:2026-09-21T17:00:00+00:00` é protocolo, não fala do cliente.

    Entrando cru no histórico, o modelo lê "17:00" — o horário em UTC — e responde sobre um horário
    que o cliente nunca pediu; foi assim que "14h" virou "esse horário às 17h". O que vai para o
    histórico tem de ser o que o cliente veria escrito: o rótulo do botão."""
    slot = grade[0].inicio
    bruto = f"slot:{slot.isoformat()}"
    assert agendador.texto_para_historico(bruto) == agendador.formatar(slot)
    assert agendador.texto_para_historico("terça às 14h") == "terça às 14h"


# --------------------------------------------------------- como o imóvel é chamado

def test_reserva_fala_do_imovel_pela_descricao_e_nao_pelo_codigo(monkeypatch, lead_no_banco, grade):
    """Relato do cliente: "Sua visita ao **SP-0282** está reservada".

    `SP-0282` é o código do cadastro. Para quem está do outro lado não significa nada, e faz a
    conversa soar como um sistema respondendo em vez de alguém atendendo. O prompt recebia o código
    no lugar do imóvel e o modelo fazia o óbvio: repetia.
    """
    capturado = _prompt_capturado(monkeypatch)
    slots = [h.inicio for h in grade]
    agendador.run(estado(f"slot:{slots[0].isoformat()}",
                         horarios_oferecidos=[s.isoformat() for s in slots]))
    corpo = capturado[0]
    assert "Apartamento 2q · Pinheiros" in corpo, "o prompt precisa do título que o cliente viu"
    assert "SP-0001" not in corpo, "o código do cadastro não pode chegar ao modelo como nome do imóvel"


def test_descricao_cai_para_o_banco_e_depois_para_generico():
    """Sem card na mão — turnos depois, ou vindo do Telegram — ainda assim não se cita o código."""
    assert agendador.descrever_imovel(None, []) == "o imóvel"
    assert "SP-" not in agendador.descrever_imovel("SP-INEXISTENTE-9999", [])


# --------------------------------------------------------------- qual imóvel visitar

def _tres() -> list[ImovelCard]:
    return [ImovelCard(id="SP-0213", titulo="Studio 29 m² · Mooca", preco=280000.0, foto=None, motivo="a"),
            ImovelCard(id="SP-0211", titulo="Apartamento 33 m² 2 vagas · Mooca", preco=420000.0, foto=None, motivo="b"),
            ImovelCard(id="SP-0204", titulo="Apartamento 40 m² · Mooca", preco=520000.0, foto=None, motivo="c")]


def test_com_varios_imoveis_na_tela_pergunta_qual_antes_do_horario(infra, grade, monkeypatch):
    """Um lead real: três imóveis na Mooca, "Agendar visita", botões de HORÁRIO sob a pergunta
    "qual desses?", um clique no horário — e a visita reservada no primeiro, que ele não escolheu."""
    monkeypatch.setattr(agendador, "llm_conversa", lambda: pytest.fail("a pergunta é fixa, sem modelo"))
    cards = _tres()
    out = agendador.run(estado("Agendar visita", imoveis_sugeridos=cards,
                               ultimos_sugeridos=[c.id for c in cards]))
    assert out["horarios_oferecidos"] == [], "horário só depois de saber qual imóvel"
    assert [o.split("|")[0] for o in out["resposta"].opcoes] == [f"imovel:{c.id}" for c in cards]
    assert out["lead"].cartao.pediu_visita, "a próxima resposta em texto livre volta para o agendador"


def test_o_botao_do_imovel_leva_aos_horarios_dele(infra, grade):
    cards = _tres()
    out = agendador.run(estado("imovel:SP-0211", imoveis_sugeridos=cards,
                               ultimos_sugeridos=[c.id for c in cards]))
    assert out["imovel_escolhido"] == "SP-0211"
    assert out["horarios_oferecidos"], "escolhido o imóvel, vêm os horários"


def test_o_horario_e_reservado_no_imovel_escolhido(infra, grade, pedidos, lead_no_banco):
    # o escolhido é o ÚLTIMO da tela (e o único que existe no banco de teste, que a visita exige)
    cards = [*_tres()[:2], ImovelCard(id="SP-0001", titulo="Apartamento 2q · Pinheiros", preco=3000.0,
                                      foto=None, motivo="c")]
    escolhido = grade[0]
    agendador.run(estado(f"slot:{escolhido.inicio.isoformat()}", imoveis_sugeridos=cards,
                         ultimos_sugeridos=[c.id for c in cards], imovel_escolhido="SP-0001",
                         horarios_oferecidos=[h.inicio.isoformat() for h in grade],
                         slots_crm={h.inicio.isoformat(): h.slot_id for h in grade}))
    assert pedidos == [("SP-0001", escolhido.slot_id)], "nunca o primeiro por omissão"


@pytest.mark.parametrize("texto, esperado", [
    ("o segundo", "SP-0211"),
    ("quero ver o studio", "SP-0213"),
    ("o com 2 vagas", "SP-0211"),
    ("o de 40", "SP-0204"),
    ("o último", "SP-0204"),
    ("Agendar visita", None),
    ("o da Mooca", None),                 # todos são da Mooca: não escolhe nada
])
def test_escolha_do_imovel_por_texto_so_quando_inequivoca(texto, esperado):
    assert agendador._escolher_pelo_texto(texto, _tres()) == esperado


# --------------------------------------------------------------- contato antes da reserva

def test_no_site_sem_contato_o_horario_espera_o_telefone(infra, grade, pedidos, monkeypatch):
    """Um lead real reservou visita sem nome e sem telefone. Agora o horário fica segurado e a
    Mora pede o contato; nada é reservado nem pedido ao CRM até ele chegar."""
    monkeypatch.setattr(agendador, "llm_conversa", lambda: pytest.fail("pedido de contato é texto fixo"))
    escolhido = grade[0]
    out = agendador.run(estado(f"slot:{escolhido.inicio.isoformat()}", sem_contato=True,
                               horarios_oferecidos=[h.inicio.isoformat() for h in grade]))
    assert out["horario_pendente"] == escolhido.inicio.isoformat()
    assert "telefone" in out["resposta"].texto and "WhatsApp" not in out["resposta"].texto
    assert pedidos == [] and out["lead"].estagio != Estagio.AGENDADO


def test_o_contato_fecha_a_reserva_do_horario_segurado(infra, grade, pedidos, monkeypatch, lead_no_banco):
    from agent.nodes import qualificador
    escolhido = grade[1]

    def extrair(cartao, msg, pergunta=""):
        return cartao.model_copy(update={"telefone_informado": "11 98765-4321"})
    monkeypatch.setattr(qualificador, "_extrair", extrair)
    out = agendador.run(estado("11 98765-4321", sem_contato=True,
                               horario_pendente=escolhido.inicio.isoformat(),
                               horarios_oferecidos=[h.inicio.isoformat() for h in grade],
                               slots_crm={h.inicio.isoformat(): h.slot_id for h in grade}))
    assert out["lead"].estagio == Estagio.AGENDADO and out["lead"].telefone == "11987654321"
    assert pedidos == [("SP-0001", escolhido.slot_id)]
    assert out["horario_pendente"] is None


def test_sem_contato_de_novo_insiste_e_oferece_o_corretor(infra, grade, pedidos, monkeypatch):
    from agent.nodes import qualificador
    monkeypatch.setattr(qualificador, "_extrair", lambda cartao, msg, pergunta="": cartao)
    out = agendador.run(estado("prefiro não passar", sem_contato=True,
                               horario_pendente=grade[0].inicio.isoformat()))
    assert pedidos == [] and out["resposta"].opcoes == ["Falar com corretor"]


def test_no_telegram_a_reserva_nao_espera_telefone(infra, grade, pedidos, lead_no_banco):
    """No Telegram o chat continua aberto e o corretor fala por ali: não há o que travar."""
    from sdr_shared.messaging import Canal
    escolhido = grade[0]
    st = estado(f"slot:{escolhido.inicio.isoformat()}", sem_contato=True,
                horarios_oferecidos=[h.inicio.isoformat() for h in grade],
                slots_crm={h.inicio.isoformat(): h.slot_id for h in grade})
    st["entrada"] = st["entrada"].model_copy(update={"canal": Canal.TELEGRAM})
    out = agendador.run(st)
    assert out["lead"].estagio == Estagio.AGENDADO


# --------------------------------------------------------------------------- entrada que não é horário válido

def test_data_que_nao_existe_reoferece_em_vez_de_derrubar_o_turno(infra, grade, lead_no_banco):
    """"31/09" levantava ValueError no `date.replace`: o turno caía, o cliente recebia a mensagem
    de problema técnico e ia parar no corretor por ter digitado uma data errada."""
    oferta = agendador.run(estado("quero visitar"))
    out = agendador.run(estado("pode ser 31/09 às 14h?",
                               horarios_oferecidos=oferta["horarios_oferecidos"],
                               slots_crm=oferta["slots_crm"]))
    assert out["resposta"].opcoes and out["resposta"].opcoes[0].startswith("slot:"), "reoferece a grade"
    assert out["lead"].estagio != Estagio.AGENDADO


@pytest.mark.parametrize("texto", ["slot:abc", "slot:2026-01-01T03:00:00+00:00"])
def test_slot_digitado_fora_da_oferta_nao_vira_visita(infra, grade, lead_no_banco, pedidos, texto):
    """`slot:` chega como texto comum: aceitar qualquer data reservava visita no passado, de
    madrugada ou fora da grade; e `slot:abc` derrubava o turno."""
    oferta = agendador.run(estado("quero visitar"))
    out = agendador.run(estado(texto, horarios_oferecidos=oferta["horarios_oferecidos"],
                               slots_crm=oferta["slots_crm"]))
    assert out["lead"].estagio != Estagio.AGENDADO and not pedidos
    assert out["resposta"].opcoes[0].startswith("slot:"), "reoferece a grade"


def test_horario_oferecido_que_ja_passou_nao_e_reservado(infra, lead_no_banco, pedidos, monkeypatch):
    """Botão antigo (Telegram) clicado depois do horário: nada de visita no passado."""
    ontem = (datetime.now(UTC) - timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
    amanha = ontem + timedelta(days=2)
    monkeypatch.setattr(agendador, "horarios_do_imovel",
                        lambda *a, **k: [Horario(inicio=amanha, slot_id="s-amanha")])
    out = agendador.run(estado(f"slot:{ontem.isoformat()}", horarios_oferecidos=[ontem.isoformat()]))
    assert out["lead"].estagio != Estagio.AGENDADO and not pedidos


# --------------------------------------------------------------- o horário segurado não prende ninguém

def _sem_extracao(monkeypatch):
    """Extração que não acha nada: o cliente respondeu sem passar contato."""
    from agent.nodes import qualificador
    monkeypatch.setattr(qualificador, "_extrair", lambda cartao, msg, pergunta="": cartao)


def test_insiste_uma_vez_so_e_depois_solta_o_horario(infra, grade, pedidos, monkeypatch):
    """Um lead real: escolheu o horário, não quis passar telefone, e a cada mensagem — sobre pet,
    sobre outro imóvel — recebia de novo "pra reservar eu preciso de um contato". A documentação
    promete insistir UMA vez; depois disso o horário é solto e a conversa segue."""
    _sem_extracao(monkeypatch)
    pendente = grade[0].inicio.isoformat()
    primeira = agendador.run(estado("prefiro não passar", sem_contato=True, horario_pendente=pendente))
    assert primeira["contato_insistido"] is True and primeira["horario_pendente"] == pendente
    segunda = agendador.run(estado("não vou passar", sem_contato=True, horario_pendente=pendente,
                                   contato_insistido=True))
    assert segunda["horario_pendente"] is None, "depois de insistir uma vez, o horário é solto"
    assert "Pra reservar" not in (segunda["resposta"].texto if segunda.get("resposta") else "")
    assert pedidos == []


def test_horario_segurado_que_ja_passou_e_descartado(infra, grade, pedidos, monkeypatch, lead_no_banco):
    """O pendente não tinha validade: o cliente sumiu, voltou dois dias depois com o telefone, e a
    Mora reservou uma visita no passado. Vencido, ele é descartado e a grade é oferecida de novo."""
    from agent.nodes import qualificador
    monkeypatch.setattr(qualificador, "_extrair", lambda cartao, msg, pergunta="":
                        cartao.model_copy(update={"telefone_informado": "11 98765-4321"}))
    ontem = (datetime.now(UTC) - timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
    out = agendador.run(estado("11 98765-4321", sem_contato=True, horario_pendente=ontem.isoformat(),
                               horarios_oferecidos=[ontem.isoformat()]))
    assert pedidos == [] and out["lead"].estagio != Estagio.AGENDADO
    assert out["horario_pendente"] is None
    assert out["resposta"].opcoes[0].startswith("slot:"), "reoferece a grade"
    assert out["lead"].telefone == "11987654321", "o contato que chegou não se perde"


def test_agendar_recusa_horario_no_passado(lead_no_banco):
    from agent.tools import agenda
    ontem = datetime.now(UTC) - timedelta(days=1)
    with pytest.raises(agenda.HorarioVencido):
        agenda.agendar("lead-ag", None, ontem)
    from sdr_shared.db import VisitaRepository
    assert not VisitaRepository().slot_livre(ontem), "horário que passou não está livre para ninguém"


def test_horario_segurado_tomado_por_outro_e_solto(infra, grade, pedidos, monkeypatch, lead_no_banco):
    """`HorarioOcupado` reoferecia a grade mas deixava o pendente apontando o horário ocupado: a
    mensagem seguinte tentava reservar o mesmo horário e "acabou de ser ocupado" se repetia."""
    from agent.tools.agenda import HorarioOcupado

    def ocupado(*a, **k):
        raise HorarioOcupado("x")
    monkeypatch.setattr(agendador, "agendar", ocupado)
    from agent.nodes import qualificador
    monkeypatch.setattr(qualificador, "_extrair", lambda cartao, msg, pergunta="":
                        cartao.model_copy(update={"telefone_informado": "11 98765-4321"}))
    out = agendador.run(estado("11 98765-4321", sem_contato=True,
                               horario_pendente=grade[0].inicio.isoformat(),
                               horarios_oferecidos=[h.inicio.isoformat() for h in grade]))
    assert out["horario_pendente"] is None
    assert out["resposta"].opcoes[0].startswith("slot:")


def test_telefone_mandado_com_a_grade_na_tela_nao_se_perde(infra, grade, pedidos, lead_no_banco):
    """O cliente viu os horários e, antes de escolher, mandou o telefone. O número sumia: na
    escolha do horário a Mora pedia o contato de novo."""
    oferecidos = [h.inicio.isoformat() for h in grade]
    st = estado("11 98765-4321", sem_contato=True, horarios_oferecidos=oferecidos)
    out = agendador.run(st)
    assert out["lead"].telefone == "11987654321"
    st2 = estado(f"slot:{oferecidos[0]}", horarios_oferecidos=oferecidos)
    st2["lead"] = out["lead"]
    out2 = agendador.run(st2)
    assert out2["lead"].estagio == Estagio.AGENDADO, "com o contato já dado, reserva direto"


def test_telefone_sem_ddd_nao_conta_como_contato(infra, grade, pedidos, monkeypatch):
    """"98765-4321" ia para `telefone_informado` e destravava a reserva, mas o lead só grava número
    com DDD: a visita saía sem telefone nenhum para o corretor ligar."""
    from agent.nodes import qualificador
    monkeypatch.setattr(qualificador, "_extrair", lambda cartao, msg, pergunta="":
                        cartao.model_copy(update={"telefone_informado": "98765-4321"}))
    out = agendador.run(estado("98765-4321", sem_contato=True,
                               horario_pendente=grade[0].inicio.isoformat()))
    assert pedidos == [] and out["lead"].estagio != Estagio.AGENDADO
    assert "DDD" in out["resposta"].texto


def test_grade_interna_conta_os_dias_no_fuso_de_brasilia():
    """Depois das 21h de Brasília já é o dia seguinte em UTC: a grade pulava o "amanhã" do cliente."""
    from zoneinfo import ZoneInfo
    from sdr_shared.db import VisitaRepository
    br = ZoneInfo("America/Sao_Paulo")
    segunda_22h = datetime(2026, 10, 5, 22, 0, tzinfo=br)          # segunda-feira, 22h em SP
    slots = VisitaRepository().horarios_disponiveis(dias=1, agora=segunda_22h)
    primeiro = slots[0].astimezone(br)
    assert (primeiro.date().isoformat(), primeiro.hour) == ("2026-10-06", 10), "amanhã (terça) às 10h"
