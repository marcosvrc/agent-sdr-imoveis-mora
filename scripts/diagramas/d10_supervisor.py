"""Ordem de decisão do supervisor (docs/architecture/fluxo-agente.md)."""
from base import Diagrama, gerar

REGRAS = [
    ("Já existe resposta neste turno, ou saltos > 1?", "encerra o turno", "cinza"),
    ("O canal é SISTEMA (pedido interno de briefing)?", "resumidor", "roxo"),
    ("A mensagem é do tipo FOLLOWUP?", "followup", "ambar"),
    ("A mensagem é do tipo REATIVACAO?", "reativador", "ambar"),
    ("PEDE_SAIR — o cliente pediu para não receber avisos?", "reativador", "ambar"),
    ("O porteiro de escopo reprovou e não houve PEDE_HUMANO?", "recusa", "vermelho"),
    ('"Falar com corretor", PEDE_HUMANO ou estágio HANDOFF?', "handoff", "verde"),
    ("Pergunta institucional, sem prefixo slot: e sem horários oferecidos?", "informacoes", "azul"),
    ("Prefixo slot:, ou horários oferecidos + ESCOLHE_HORARIO?", "agendador", "azul"),
    ('"Agendar visita", PEDE_VISITA ou pediu_visita — e estágio ≠ AGENDADO?', "agendador", "azul"),
    ('"Ver outros" ou PEDE_OPCOES?', "consultor", "azul"),
    ("Cartão completo e ainda sem imóveis sugeridos?", "consultor", "azul"),
    ("Cartão incompleto?", "qualificador", "azul"),
]


def montar() -> Diagrama:
    d = Diagrama(
        nome="supervisor", titulo="Ordem de decisão do supervisor",
        subtitulo="Treze regras determinísticas antes de gastar um token",
        largura=1700, altura=1800, rodape_dir="MORA · ROTEAMENTO",
        alt=("Escada de decisão do supervisor: cada regra é avaliada na ordem; a primeira que "
             "casa define o especialista, e só o que sobra vai ao modelo de roteamento."))

    y0, passo = 190, 100
    for i, (pergunta, destino, tom) in enumerate(REGRAS):
        y = y0 + i * passo
        d.cartao(60, y, 900, 72, pergunta, None, None, "azul", pequeno=True, destaque="azul")
        d.add(f'<text x="34" y="{y + 36}" class="t-mini" text-anchor="middle">{i + 1}</text>')
        d.aresta([(960, y + 36), (1100, y + 36)], tom, "sim", rot_xy=(1030, y + 20))
        d.caixa(1100, y + 6, 300, 60, destino, "", tom)
        if i < len(REGRAS) - 1:
            d.aresta([(510, y + 72), (510, y + passo)], "cinza", "não",
                     rot_xy=(524, y + 86), ancora="start")

    y = y0 + len(REGRAS) * passo
    d.aresta([(510, y - 28), (510, y + 10)], "cinza", "não", rot_xy=(524, y - 6), ancora="start")
    d.cartao(60, y + 10, 900, 96, "Modelo de roteamento (papel barato, temperatura 0)",
             ["Resposta restrita a qualificador, consultor, agendador, handoff ou informacoes —",
              "qualquer outra coisa vira qualificador. Lead AGENDADO nunca volta ao agendador."],
             "faisca", "roxo", pequeno=True, destaque="roxo")

    d.nota(850, y + 140, 1580, [
        "A ordem importa: PEDE_SAIR vem antes do porteiro de escopo (senão “não quero mais nada” seria recusado como fora de assunto), e o pedido de humano",
        "vence a recusa. Depois do especialista, _rotear encerra o turno quando há resposta, quando saltos chega a MAX_SALTOS = 4, ou quando o nó devolveu",
        "sem mudar a decisão — repetição sem mudança é fim de turno, não nova tentativa."])

    d.legenda([("azul", "Atendimento"), ("verde", "Passagem ao humano"),
               ("ambar", "Iniciado pela Mora"), ("vermelho", "Fora de escopo")], y=1750)
    d.rodape("Mora · supervisor")
    return d


if __name__ == "__main__":
    print("\n".join(gerar(montar())))
