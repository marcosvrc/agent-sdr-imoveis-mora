"""Sequência de um turno do agente (docs/architecture/fluxo-agente.md)."""
from base import Diagrama, gerar


def montar() -> Diagrama:
    d = Diagrama(
        nome="turno", titulo="Fluxo do agente e do modelo",
        subtitulo="Um turno, do quadro que chega ao canal até a resposta entregue",
        largura=2060, altura=1650,
        alt=("Sequência de um turno: o canal publica no Redis, o handler prepara o contexto, o "
             "grafo decide e chama o modelo, e o handler persiste, despacha, espelha no CRM e "
             "reagenda o follow-up."))

    colunas = [
        ("Canal", "Telegram · web", "aviao"),
        ("Redis", "broker · inbound", "camadas"),
        ("Handler", "handler.processar", "codigo"),
        ("Postgres", "lead · auditoria · turnos", "banco"),
        ("Grafo", "supervisor + especialistas", "faisca"),
        ("Modelo", "conversa · roteamento", "faisca"),
        ("Saída", "outbound · events · resumir", "fila"),
        ("CRM", "porta MCP", "tomada"),
        ("Scheduler", "follow-up", "relogio"),
    ]
    d.sequencia(colunas, y=128, larg=210, gap=12, ate=1512)
    C, R, H, P, G, M, O, K, S = range(9)

    d.faixa(246, 394, "01 Recepção e contexto", "azul")
    d.passo(C, R, 332, ["MensagemNormalizada (JSON)"], 1, "azul")
    d.ativacao(H, 368, 1462, "azul")
    d.passo(R, H, 386, ['consume("inbound") · lock por lead'], 2, "azul")
    d.passo_proprio(H, 452, ["transcrever se áudio · PING no broker · vazão",
                             "sem barramento o turno é recusado antes do modelo"], 3, "azul")
    d.passo(H, P, 530, ["carregar/criar lead · registrar msg \"in\" · marcar atividade"], 4, "azul")
    d.passo(H, K, 596, ["reconhecer(lead) — só com contato e ainda não procurado"], 5, "verde")

    d.faixa(660, 420, "02 Raciocínio e resposta", "roxo")
    d.passo(H, G, 746, ["invoke(entrada_grafo, thread_id=lead.id)"], 6, "roxo")
    d.ativacao(G, 734, 1035, "roxo")
    d.passo_proprio(G, 812, ["supervisor: regras determinísticas → porteiro de escopo",
                             "→ modelo de roteamento só na ambiguidade"], 7, "roxo")
    d.passo(G, M, 894, ["especialista chama o modelo (persona + blindagem + histórico podado)"], 8, "roxo")
    d.passo(M, G, 958, ["texto → sanear()"], 9, "roxo", tracejada=True)
    d.passo(G, H, 1022, ["{lead, resposta, próximo, ...}"], 10, "roxo", tracejada=True)

    d.faixa(1100, 420, "03 Persistência, despacho e encerramento", "verde")
    d.passo(H, P, 1186, ["score e temperatura · upsert do lead · auditoria · msg \"out\""], 11, "cinza")
    d.passo(H, O, 1250, ["despachar(outbound-canal) · publicar_eventos(events, resumir)"], 12, "verde")
    d.passo(H, K, 1314, ["publicar_turno — depois do despacho; falha vai para crm_pendencias"], 13, "verde")
    d.passo(H, S, 1378, ["reagendar_followup / cancel"], 14, "verde")
    d.passo(H, P, 1440, ["registrar_turno (tabela turnos)"], 15, "cinza")
    d.passo(O, C, 1500, ["RespostaAgente renderizada pelo adaptador do canal"], 16, "verde", tracejada=True)

    d.legenda([("azul", "Chamada e publicação"), ("roxo", "Raciocínio e modelo"),
               ("verde", "Entrega, CRM e agenda"), ("cinza", "Persistência")], y=1600)
    d.rodape("fluxo do agente")
    return d


if __name__ == "__main__":
    print("\n".join(gerar(montar())))
