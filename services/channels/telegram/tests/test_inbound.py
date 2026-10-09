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


# ------------------------------------------------- /novo: recomeçar a conversa no modo de teste

def _comando(texto: str) -> dict:
    return {"update_id": 20, "message": {**TEXTO["message"], "text": texto}}


class _Repos:
    """Leads e canais em memória: quem é dono do chat agora."""
    def __init__(self):
        self.canais, self.leads = {"555": "tg_555"}, {"tg_555"}

    def preparar(self, monkeypatch):
        repos = self

        class Leads:
            def upsert(self, lead): repos.leads.add(lead.id); return lead
            def get_por_canal(self, canal, ident):
                from types import SimpleNamespace
                return SimpleNamespace(id=repos.canais[ident]) if ident in repos.canais else None

        class Canais:
            def vincular(self, lead_id, canal, ident): repos.canais[ident] = lead_id

        monkeypatch.setattr(inbound, "LeadRepository", Leads)
        monkeypatch.setattr(inbound, "CanalRepository", Canais)
        return self


def test_novo_no_perfil_local_comeca_lead_novo_com_ola(monkeypatch):
    import json
    from sdr_shared.config import get_settings
    monkeypatch.setattr(get_settings(), "profile", "local")
    repos, broker = _Repos().preparar(monkeypatch), Broker()
    monkeypatch.setattr(inbound, "get_broker", lambda: broker)
    inbound.processar_lote([_comando("/novo")], None)
    msg = json.loads(broker.publicados[0])
    assert msg["lead_id"].startswith("tg_555_") and msg["lead_id"] != "tg_555"
    assert msg["conteudo"] == "Olá!", "a Mora recebe um início de conversa, não o comando"
    assert repos.canais["555"] == msg["lead_id"], "as próximas mensagens do chat vão para o lead novo"
    assert "tg_555" in repos.leads, "o lead antigo continua lá, com o histórico"


def test_novo_fora_do_perfil_local_e_mensagem_comum(monkeypatch):
    """Em produção, /novo de um cliente não pode jogar fora o atendimento dele."""
    import json
    from sdr_shared.config import get_settings
    monkeypatch.setattr(get_settings(), "profile", "producao")
    repos, broker = _Repos().preparar(monkeypatch), Broker()
    monkeypatch.setattr(inbound, "get_broker", lambda: broker)
    monkeypatch.setattr(inbound, "_resolver_lead", lambda chat_id, nome: repos.canais[chat_id])
    inbound.processar_lote([_comando("/novo")], None)
    msg = json.loads(broker.publicados[0])
    assert msg["lead_id"] == "tg_555" and repos.canais["555"] == "tg_555"


def test_cada_mensagem_publicada_avisa_quem_liga_o_digitando(monkeypatch):
    broker, avisados = Broker(), []
    _preparar(monkeypatch, broker)
    inbound.processar_lote([_update(10), _update(11)], None, ao_publicar=lambda m: avisados.append(m.lead_id))
    assert avisados == ["tg_555", "tg_555"]
