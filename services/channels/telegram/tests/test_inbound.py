"""O offset do getUpdates só anda depois que o update está no broker."""
import canal_telegram.inbound as inbound

TEXTO = {"message": {"message_id": 1, "chat": {"id": 555}, "from": {"id": 555, "first_name": "Marcos"},
                     "text": "oi"}}


def _update(n: int) -> dict:
    return {"update_id": n, **TEXTO}


class Broker:
    def __init__(self, fora_a_partir_de: int | None = None):
        self.publicados, self.fora = [], fora_a_partir_de

    def publish(self, topico, corpo, key):
        if self.fora is not None and len(self.publicados) >= self.fora:
            raise ConnectionError("Redis fora do ar")
        self.publicados.append(corpo)


def _preparar(monkeypatch, broker):
    monkeypatch.setattr(inbound, "get_broker", lambda: broker)
    monkeypatch.setattr(inbound, "_resolver_lead", lambda chat_id, nome: f"tg_{chat_id}")


def test_broker_fora_nao_avanca_o_offset(monkeypatch):
    """Com o Redis fora, o offset andava antes da publicação: o próximo getUpdates confirmava o
    update ao Telegram e a mensagem do cliente se perdia."""
    _preparar(monkeypatch, Broker(fora_a_partir_de=1))
    offset, completo = inbound.processar_lote([_update(10), _update(11), _update(12)], None)
    assert completo is False
    assert offset == 11, "o 10 foi publicado; o 11 tem de voltar no próximo getUpdates"


def test_broker_no_ar_confirma_o_lote_inteiro(monkeypatch):
    broker = Broker()
    _preparar(monkeypatch, broker)
    offset, completo = inbound.processar_lote([_update(10), _update(11)], 5)
    assert (offset, completo) == (12, True) and len(broker.publicados) == 2


def test_update_intraduzivel_e_pulado_para_nao_travar_o_bot(monkeypatch):
    broker = Broker()
    _preparar(monkeypatch, broker)

    original = inbound.parse_inbound

    def quebra(u, resolver_lead):
        if u["update_id"] == 10:
            raise ValueError("formato inesperado")
        return original(u, resolver_lead=resolver_lead)
    monkeypatch.setattr(inbound, "parse_inbound", quebra)
    offset, completo = inbound.processar_lote([_update(10), _update(11)], None)
    assert (offset, completo) == (12, True) and len(broker.publicados) == 1
