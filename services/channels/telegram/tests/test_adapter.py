from canal_telegram.adapter import parse_inbound, render
from sdr_shared.messaging import RespostaAgente, TipoMensagem
from sdr_shared.models import ImovelCard

MSG_TEXTO = {"message": {"message_id": 1, "chat": {"id": 555, "type": "private"},
                          "from": {"id": 555, "first_name": "Marcos"}, "text": "/start IMOVEL-SP-0001"}}
MSG_VOZ = {"message": {"message_id": 2, "chat": {"id": 555}, "from": {"id": 555, "first_name": "Marcos"},
                        "voice": {"file_id": "file-1", "duration": 3}}}
CALLBACK = {"callback_query": {"id": "cb1", "from": {"id": 555, "first_name": "Marcos"},
                                "message": {"chat": {"id": 555}}, "data": "slot:2026-09-10T13:00:00+00:00"}}


def _resolver(chat_id, nome):
    return f"tg_{chat_id}"


def test_parse_texto_com_deep_link():
    msgs = parse_inbound(MSG_TEXTO, resolver_lead=_resolver)
    assert len(msgs) == 1 and msgs[0].tipo == TipoMensagem.TEXTO
    assert msgs[0].meta["imovel_origem"] == "SP-0001" and msgs[0].meta["nome"] == "Marcos"
    assert msgs[0].identificador_canal == "555" and msgs[0].lead_id == "tg_555"


def test_parse_voz():
    msgs = parse_inbound(MSG_VOZ, resolver_lead=_resolver)
    assert msgs[0].tipo == TipoMensagem.AUDIO and msgs[0].meta["telegram_file_id"] == "file-1"


def test_parse_callback_query_vira_botao():
    msgs = parse_inbound(CALLBACK, resolver_lead=_resolver)
    assert msgs[0].tipo == TipoMensagem.BOTAO and msgs[0].conteudo.startswith("slot:")


def test_parse_ignora_update_sem_message_ou_callback():
    assert parse_inbound({"edited_message": {}}, resolver_lead=_resolver) == []


def test_render_texto_simples():
    r = RespostaAgente(lead_id="l", texto="Quer comprar, alugar ou investir?")
    m = render("555", r)
    assert m == [{"_method": "sendMessage", "chat_id": "555", "text": r.texto}]


def test_render_com_opcoes_vira_teclado_inline():
    r = RespostaAgente(lead_id="l", texto="Escolha um horário",
                        opcoes=["slot:2026-09-10T13:00:00|qui 10/09 às 10h", "slot:2026-09-11T13:00:00|sex 11/09 às 10h"])
    m = render("555", r)
    teclado = m[0]["reply_markup"]["inline_keyboard"]
    assert len(teclado) == 2 and teclado[0][0]["callback_data"].startswith("slot:") and teclado[0][0]["text"] == "qui 10/09 às 10h"


def test_render_card_de_imovel_vira_sendphoto_antes_do_texto():
    r = RespostaAgente(lead_id="l", texto="Olha este",
                        imoveis=[ImovelCard(id="SP-0001", titulo="Apto 2q · Brooklin", preco=780000, foto="https://x/1.jpg", motivo="perto do metrô")],
                        opcoes=["Agendar visita"])
    m = render("555", r)
    assert m[0]["_method"] == "sendPhoto" and "R$ 780.000" in m[0]["caption"]
    assert m[1]["_method"] == "sendMessage" and m[1]["reply_markup"]["inline_keyboard"][0][0]["text"] == "Agendar visita"
