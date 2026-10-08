"""Ordem de decisão do supervisor (docs/architecture/fluxo-agente.md)."""
from base import Diagrama, gerar

REGRAS = [
    ("Já existe resposta neste turno, ou saltos > 1?", "encerra o turno", "cinza"),
    ("O canal é SISTEMA (pedido interno de briefing)?", "resumidor", "roxo"),
    ("A mensagem é do tipo FOLLOWUP?", "followup", "ambar"),
    ("A mensagem é do tipo REATIVACAO?", "reativador", "ambar"),
    ("PEDE_SAIR — o cliente pediu para não receber avisos?", "reativador", "ambar"),
    ("O porteiro de escopo reprovou e não houve pedido de humano?", "recusa", "vermelho"),
    ('"Falar com corretor", pedido de humano ou estágio HANDOFF?', "handoff", "verde"),
    ("Horário segurado, contato já insistido; não é contato, slot:, opções nem institucional?", "agendador", "azul"),
    ("Botão “visitar este imóvel” (prefixo imovel:)?", "agendador", "azul"),
    ("Botão de ampliação da busca (prefixo ajuste:)?", "consultor", "azul"),
    ("Horário segurado e chegou contato, slot: ou até 4 palavras não institucionais?", "agendador", "azul"),
    ("Pergunta institucional ou consultiva, sem slot: e sem escolher horário da grade?", "informacoes", "azul"),
    ("Intenção já é compra ou aluguel e o cliente pediu a outra?", "qualificador", "azul"),
    ("Pede detalhes de um imóvel já mostrado (PEDE_DETALHES)?", "consultor", "azul"),
    ("Prefixo slot:, ou horários oferecidos + ESCOLHE_HORARIO?", "agendador", "azul"),
    ('"Agendar visita", ou PEDE_VISITA sem adiar a visita?', "agendador", "azul"),
    ('"Ver outros" ou PEDE_OPCOES?', "consultor", "azul"),
    ("pediu_visita ligado, estágio ≠ AGENDADO e sem adiar a visita?", "agendador", "azul"),
    ("Cartão completo e a mensagem é só um contato?", "qualificador", "azul"),
    ("A Mora perguntou como ampliar e o cartão está completo?", "consultor", "azul"),
    ("Cartão completo e ainda sem imóveis sugeridos?", "consultor", "azul"),
    ("Cartão incompleto?", "qualificador", "azul"),
]



def montar() -> Diagrama:
    d = Diagrama(
        nome="supervisor", titulo="Ordem de decisão do supervisor",
        subtitulo="Vinte e duas regras determinísticas antes de gastar um token",
        largura=1700, altura=2650,
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
    d.cartao(60, y + 10, 900, 118, "Modelo de roteamento (papel barato, temperatura 0)",
             ["Vale a primeira de qualificador, consultor, agendador, informacoes ou handoff na",
              "resposta; nada disso vira qualificador. AGENDADO não volta ao agendador; handoff",
              "em até 3 palavras sem pedido de pessoa volta ao especialista."],
             "faisca", "roxo", pequeno=True, destaque="roxo")

    d.nota(850, y + 165, 1580, [
        "A ordem importa: PEDE_SAIR vem antes do porteiro de escopo (senão “não quero mais nada” seria recusado como fora de assunto), e o pedido de humano",
        "vence a recusa. Com horário segurado, pedir outras opções (ou fazer pergunta institucional depois da insistência) solta o horário e a mensagem segue",
        "para as regras seguintes. Depois do especialista, _rotear encerra o turno quando há resposta, quando saltos chega a MAX_SALTOS = 4, ou quando o nó",
        "devolveu sem mudar a decisão — repetição sem mudança é fim de turno, não nova tentativa."])

    d.legenda([("azul", "Atendimento"), ("verde", "Passagem ao humano"),
               ("ambar", "Iniciado pela Mora"), ("vermelho", "Fora de escopo")], y=2600)
    d.rodape("supervisor")
    return d


if __name__ == "__main__":
    print("\n".join(gerar(montar())))
