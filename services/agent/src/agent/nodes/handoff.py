"""Encaminha ao corretor: escolhe quem atende (região + menor carga), muda estágio, avisa o cliente pelo nome.
O roteador de canal passa a entregar ao painel. Sem corretor cadastrado, segue sem responsável (o painel avisa)."""
from sdr_shared.db import CorretorRepository, auditar, notificar
from sdr_shared.messaging import RespostaAgente, Acao
from sdr_shared.models import Estagio
from ..state import AgentState


def escolher_corretor(lead) -> str | None:
    if lead.corretor_id and (c := CorretorRepository().get(lead.corretor_id)) and c.ativo:
        return c.nome                                        # já tem responsável: mantém
    if co := CorretorRepository().escolher(lead.cartao.regiao):
        lead.corretor_id = co.id
        return co.nome
    return None


def run(state: AgentState) -> dict:
    lead = state["lead"]
    lead.estagio = Estagio.HANDOFF
    corretor = escolher_corretor(lead)
    auditar(acao="lead.encaminhado_corretor", entidade="lead", entidade_id=lead.id,
            ator_tipo="agente", ator_nome="Mora", origem=str(state["entrada"].canal.value),
            dados={"corretor_id": lead.corretor_id, "corretor": corretor, "regiao": lead.cartao.regiao,
                   "temperatura": str(lead.temperatura), "score": lead.score},
            resultado="ok" if corretor else "erro",
            detalhe=None if corretor else "nenhum corretor ativo para a região")
    quem = lead.nome or lead.telefone or lead.id
    busca = lead.cartao.bairros or ([lead.cartao.regiao] if lead.cartao.regiao else [])
    notificar(tipo="lead.encaminhado", corretor_id=lead.corretor_id, lead_id=lead.id,
              titulo=f"{quem} está esperando você",
              detalhe=f"Lead {lead.temperatura} · {lead.cartao.intencao}"
                      + (f" em {', '.join(str(b) for b in busca)}" if busca else "")
                      + (". Sem telefone: responda pelo painel." if not lead.telefone else f" · {lead.telefone}"),
              dados={"temperatura": str(lead.temperatura), "score": lead.score},
              chave=f"handoff-{lead.followups_enviados}")
    nome = f", {lead.nome}" if lead.nome else ""
    if corretor:
        primeiro = corretor.split()[0]
        texto = f"Combinado{nome}! Vou passar nossa conversa para {primeiro}, da equipe de corretores, que continua com você por aqui em instantes."
    else:
        texto = f"Combinado{nome}! Vou passar nossa conversa para um corretor, que continua com você por aqui em instantes."
    return {"lead": lead, "resposta": RespostaAgente(lead_id=lead.id, acao=Acao.HANDOFF, texto=texto)}
