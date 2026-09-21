"""Publicação de um turno no CRM, por MCP (docs/architecture/componentes.md)."""
from base import Diagrama, gerar


def montar() -> Diagrama:
    d = Diagrama(
        nome="crm-publicacao", titulo="Publicação de um turno no CRM",
        subtitulo="A porta é o MCP; a falha não derruba a conversa, vai para a fila",
        largura=1820, altura=1280, rodape_dir="MORA · PONTE COM O CRM",
        alt=("Sequência da publicação no CRM: o handler despacha a resposta primeiro, o publicador "
             "abre uma sessão MCP e chama uma ferramenta por fato; se falhar, o turno vai para "
             "crm_pendencias."))

    colunas = [
        ("handler", "agent.handler", "codigo"),
        ("publicador", "shared/crm", "fila"),
        ("CRMviaMCP", "sessão por turno", "tomada"),
        ("crm-mcp", ":8200/mcp", "engrenagem"),
        ("crm-api", ":8100 · REST", "predio"),
    ]
    d.sequencia(colunas, y=128, larg=250, gap=26, ate=1150)
    H, P, A, M, R = range(5)

    d.ativacao(H, 268, 430, "azul")
    d.passo_proprio(H, 300, ["despacha a resposta ao cliente — o CRM vem depois,",
                             "para que um CRM fora do ar nunca atrase o atendimento"], 1, "azul")
    d.passo(H, P, 400, ["publicar_turno(lead, entrada, texto_saida, ...)"], 2, "azul")
    d.ativacao(P, 388, 1090, "verde")
    d.passo(P, A, 470, ["sessao() — uma conexão para o turno inteiro"], 3, "verde")
    d.ativacao(A, 458, 1000, "verde")
    d.passo(A, M, 540, ["MCP initialize (Bearer SDR_CRM_TOKEN)"], 4, "verde")

    d.quadro(430, 596, 1330, 330, "para cada fato do turno", "roxo")
    d.passo(P, A, 668, ["garantir_lead · garantir_oportunidade · registrar_interacao",
                        "atualizar_preferencias · mover_estagio · encaminhar"], 5, "roxo")
    d.passo(A, M, 752, ["tools/call {operation_id, expected_version}"], 6, "roxo")
    d.passo(M, R, 824, ["REST: Bearer CRM_API_TOKEN · Idempotency-Key · If-Match"], 7, "roxo")
    d.passo(R, M, 878, ["{ok, data} ou {error.code}"], 8, "roxo", tracejada=True)
    d.passo(M, A, 908, ["structuredContent"], None, "roxo", tracejada=True)

    d.quadro(430, 966, 1330, 124, "se a sessão veio inerte ou algum fato não subiu", "vermelho")
    d.passo_proprio(P, 1030, ["grava em crm_pendencias — o scheduler republica",
                              "com espera dobrada, até 1 h, por 30 tentativas"], 9, "vermelho")

    d.nota(910, 1150, 1700, [
        "sessao() nunca levanta: com o CRM fora do ar ela entrega uma sessão inerte, e é o publicador voltar sem lead criado que denuncia a queda.",
        "Repetir é seguro — operation_id e external_event_id são derivados do lead e do fato, não de um contador nem do relógio."])
    d.legenda([("azul", "Turno do cliente"), ("verde", "Abertura da sessão"),
               ("roxo", "Uma ferramenta por fato"), ("vermelho", "Fila de pendências")], y=1240)
    return d


if __name__ == "__main__":
    print("\n".join(gerar(montar())))
