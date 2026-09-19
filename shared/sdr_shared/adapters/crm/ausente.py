"""Adaptador para quando não há CRM — o padrão.

Não é um dublê de teste: é o modo normal de rodar a Mora sozinha, na demonstração, no
desenvolvimento e na suíte. Sem ele, cada nó precisaria de um `if crm:` e a ausência de CRM viraria
uma ramificação espalhada pelo grafo, que é onde os caminhos não testados se escondem.
"""
from contextlib import contextmanager
from collections.abc import Iterator


class _Nada:
    def garantir_lead(self, lead): return None
    def garantir_oportunidade(self, lead, crm_lead_id): return None
    def registrar_interacao(self, crm_lead_id, **k): return False
    def atualizar_preferencias(self, crm_opportunity_id, lead, versao): return None
    def mover_estagio(self, crm_opportunity_id, **k): return None
    def encaminhar(self, crm_lead_id, crm_opportunity_id, **k): return False
    def buscar_lead_por_contato(self, **k): return None
    def consultar_lead(self, crm_lead_id): return None
    def consultar_oportunidade(self, crm_opportunity_id): return None
    def imovel_por_codigo(self, codigo): return None
    def listar_imoveis(self, **k): return [], None
    def horarios_livres(self, crm_property_id, **k): return []
    def solicitar_visita(self, **k): return None
    def registrar_interesse(self, **k): return None
    def consultar_historico(self, crm_lead_id, **k): return []


class CRMAusente:
    def habilitado(self) -> bool:
        return False

    @contextmanager
    def sessao(self) -> Iterator:
        yield _Nada()
