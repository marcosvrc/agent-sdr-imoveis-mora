from canal_whatsapp.adapter import parse_inbound, render
from sdr_shared.messaging import RespostaAgente, TipoMensagem
from sdr_shared.models import ImovelCard

PAYLOAD = {"entry": [{"changes": [{"value": {
    "contacts": [{"wa_id": "5511999990000", "profile": {"name": "Marcos"}}],
    "messages": [
        {"id": "wamid.1", "from": "5511999990000", "type": "text", "text": {"body": "Olá! Vi o IMOVEL-SP-0001 no site"}},
        {"id": "wamid.2", "from": "5511999990000", "type": "interactive", "interactive": {"type": "list_reply", "list_reply": {"id": "slot:2026-09-10T13:00:00+00:00", "title": "qui 10/09 às 10h"}}},
        {"id": "wamid.3", "from": "5511999990000", "type": "audio", "audio": {"id": "media-1"}},
    ]}}]}]}


def test_parse():
    msgs = parse_inbound(PAYLOAD, resolver_lead=lambda tel, nome: f"lead_{tel[-4:]}")
    assert [m.tipo for m in msgs] == [TipoMensagem.TEXTO, TipoMensagem.BOTAO, TipoMensagem.AUDIO]
    assert msgs[0].meta["imovel_origem"] == "SP-0001" and msgs[0].meta["nome"] == "Marcos"
    assert msgs[1].conteudo.startswith("slot:") and msgs[2].meta["media_id"] == "media-1"


def test_render_botoes_lista_cards():
    tel = "5511999990000"
    r = RespostaAgente(lead_id="l", texto="Quer comprar, alugar ou investir?", opcoes=["Comprar", "Alugar", "Investir"])
    m = render(tel, r)
    assert m[0]["interactive"]["type"] == "button" and len(m[0]["interactive"]["action"]["buttons"]) == 3
    r = RespostaAgente(lead_id="l", texto="Escolha um horário", opcoes=[f"slot:2026-09-1{i}T13:00:00|qui 1{i}/09 às 10h" for i in range(5)])
    m = render(tel, r)
    rows = m[0]["interactive"]["action"]["sections"][0]["rows"]
    assert m[0]["interactive"]["type"] == "list" and rows[0]["id"].startswith("slot:") and rows[0]["title"] == "qui 10/09 às 10h"
    r = RespostaAgente(lead_id="l", texto="Olha estes", imoveis=[ImovelCard(id="SP-0001", titulo="Apto 2q · Brooklin", preco=780000, foto="https://x/1.jpg", motivo="perto do metrô")],
                       opcoes=["Agendar visita", "Ver outros", "Falar com corretor"])
    m = render(tel, r)
    assert m[0]["type"] == "image" and "R$ 780.000" in m[0]["image"]["caption"] and m[1]["interactive"]["type"] == "button"
