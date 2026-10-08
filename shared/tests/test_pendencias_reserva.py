"""Drenagem da fila do CRM com dois schedulers ao mesmo tempo."""
import json
import os
from contextlib import contextmanager

os.environ.setdefault("SDR_DATABASE_DSN", "postgresql://sdr:sdr@localhost:5433/sdr_test")
from sdr_shared.db.guarda_teste import exigir_banco_de_teste; exigir_banco_de_teste()   # noqa: E702

import sdr_shared.ports as portas
from sdr_shared.crm import pendencias, publicador
from sdr_shared.db import LeadRepository, get_pool
from sdr_shared.messaging import Canal, MensagemNormalizada, TipoMensagem
from sdr_shared.models import Lead


class CrmFalso:
    def habilitado(self):
        return True

    @contextmanager
    def sessao(self):
        yield object()


def test_dois_schedulers_nao_publicam_a_mesma_linha(monkeypatch):
    """O segundo scheduler começa a drenar enquanto o primeiro ainda publica o lote. Sem reserva,
    os dois liam as mesmas linhas vencidas e o CRM recebia o turno duas vezes."""
    LeadRepository().upsert(Lead(id="l_pend_reserva"))
    entrada = MensagemNormalizada(lead_id="l_pend_reserva", canal=Canal.WEB, tipo=TipoMensagem.TEXTO,
                                  identificador_canal="s", conteudo="oi")
    with get_pool().connection() as c:
        c.execute("DELETE FROM crm_pendencias")
        for i in range(3):
            c.execute("INSERT INTO crm_pendencias (lead_id, chave, turno) VALUES (%s, %s, %s)",
                      ("l_pend_reserva", f"reserva:{i}",
                       json.dumps({"entrada": entrada.model_dump(mode="json"), "id_entrada": i})))

    publicados, segundo = [], {}

    def publicar(_s, lead, _e, _t, _a, id_entrada, _id_saida):
        publicados.append(id_entrada)
        if not segundo:                       # o outro scheduler acorda no meio do lote
            segundo.update(pendencias.drenar())
        return True

    monkeypatch.setattr(portas, "get_crm", lambda: CrmFalso())
    monkeypatch.setattr(publicador, "_publicar", publicar)

    primeiro = pendencias.drenar()

    assert sorted(publicados) == [0, 1, 2], f"turno publicado mais de uma vez: {publicados}"
    assert primeiro["publicadas"] == 3 and segundo["publicadas"] == 0
    assert pendencias.pendentes() == 0
