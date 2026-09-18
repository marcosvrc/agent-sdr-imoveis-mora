"""Correspondência entre o lead da Mora e o par (cliente, oportunidade) do CRM.

A tabela fica no banco da MORA, e não no do CRM. É dado da Mora sobre a própria integração: quem
precisa saber "para onde eu publiquei este lead" é quem publica. Guardar isso do outro lado
obrigaria o CRM a conhecer a existência da Mora — e a decisão D-01 é justamente que ele não
conheça.

A versão vem junto porque é o `If-Match` da próxima escrita. Guardá-la evita um GET a cada turno;
quando ela ficar velha (alguém editou pelo painel), o CRM responde 412 e o publicador relê. Isso é
funcionamento normal, não erro.
"""
from dataclasses import dataclass

from ..db.connection import get_pool


@dataclass(frozen=True)
class Vinculo:
    lead_id: str
    crm_lead_id: str
    crm_opportunity_id: str
    crm_version: int


def buscar(lead_id: str) -> Vinculo | None:
    with get_pool().connection() as conn:
        linha = conn.execute("SELECT * FROM crm_vinculo WHERE lead_id = %s", (lead_id,)).fetchone()
    if linha is None:
        return None
    return Vinculo(lead_id=linha["lead_id"], crm_lead_id=str(linha["crm_lead_id"]),
                   crm_opportunity_id=str(linha["crm_opportunity_id"]),
                   crm_version=linha["crm_version"])


def salvar(lead_id: str, crm_lead_id: str, crm_opportunity_id: str, versao: int) -> Vinculo:
    with get_pool().connection() as conn:
        conn.execute(
            """INSERT INTO crm_vinculo (lead_id, crm_lead_id, crm_opportunity_id, crm_version)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (lead_id) DO UPDATE SET crm_lead_id = EXCLUDED.crm_lead_id,
                   crm_opportunity_id = EXCLUDED.crm_opportunity_id,
                   crm_version = EXCLUDED.crm_version, atualizado_em = now()""",
            (lead_id, crm_lead_id, crm_opportunity_id, versao))
    return Vinculo(lead_id, crm_lead_id, crm_opportunity_id, versao)


def atualizar_versao(lead_id: str, versao: int) -> None:
    with get_pool().connection() as conn:
        conn.execute("UPDATE crm_vinculo SET crm_version = %s, atualizado_em = now() "
                     "WHERE lead_id = %s", (versao, lead_id))
