"""Máquina de estados do lead, leitura de negócio (docs/ARCHITECTURE.md)."""
from base import Diagrama, gerar


def montar() -> Diagrama:
    d = Diagrama(
        nome="estados-negocio", titulo="Jornada do lead",
        subtitulo="Máquina de estados, na leitura de quem opera",
        largura=1960, altura=1180,
        alt=("Jornada do lead: novo, qualificando, qualificado, agendado e handoff, com o desvio "
             "de inatividade e a volta por nova oportunidade."))

    d.add('<text x="40" y="150" class="t-grp">01 QUALIFICAÇÃO E ENCAMINHAMENTO</text>')
    d.marco(80, 305)
    d.estado(130, 250, 300, 110, "Novo", "lead recebido", "balao", "azul")
    d.estado(570, 250, 320, 110, "Qualificando", "coletando as preferências", "lista", "azul")
    d.estado(1030, 250, 320, 110, "Qualificado", "cartão completo + score", "certo", "verde")
    d.estado(1490, 250, 320, 110, "Agendado", "visita reservada", "agenda", "roxo")
    d.estado(1490, 640, 320, 110, "Handoff", "com o corretor", "pessoa", "verde")
    d.marco(1650, 860, "fim do fluxo automatizado", inicio=False)

    d.aresta([(92, 305), (130, 305)], "tinta2")
    d.aresta([(430, 305), (570, 305)], "tinta2", rot_xy=(500, 272), rot_linhas=["intenção", "identificada"])
    d.aresta([(650, 250), (650, 206), (810, 206), (810, 250)], "tinta2", raio=10,
             rot_xy=(730, 176), rot_linhas=["preenche o cartão: região,", "preço, quartos, urgência"])
    d.aresta([(890, 305), (1030, 305)], "tinta2", rot_xy=(960, 272), rot_linhas=["cartão completo", "+ score"])
    d.aresta([(1350, 305), (1490, 305)], "tinta2", rot_xy=(1420, 272), rot_linhas=["reserva de visita", "(só pessoa confirma)"])
    d.aresta([(1650, 360), (1650, 640)], "tinta2", rot_xy=(1664, 480), ancora="start",
             rot_linhas=["o cliente", "pede corretor"])
    d.aresta([(1190, 360), (1190, 590), (1570, 590), (1570, 640)], "tinta2", raio=14,
             rot_xy=(1204, 420), ancora="start", rot_linhas=["corretor assume,", "falha do turno ou", "teto de orçamento"])
    d.aresta([(1650, 750), (1650, 838)], "tinta2")

    # -------------------------------------------------- inatividade
    d.painel(100, 500, 1050, 420, "02 Inatividade e reengajamento", "o silêncio do cliente tem cadência própria")
    d.estado(570, 570, 320, 110, "Inativo", "aguardando retorno", "relogio", "ambar")
    d.estado(150, 750, 320, 110, "Frio", "esgotaram as tentativas", "gelo", "cinza")

    for x in (280, 1110):
        d.aresta([(x, 360), (x, 430)], "ambar", tracejada=True, ponta=False)
    d.aresta([(730, 360), (730, 430)], "ambar", tracejada=True, ponta=False)
    d.aresta([(280, 430), (1110, 430)], "ambar", tracejada=True, ponta=False)
    d.aresta([(730, 430), (730, 570)], "ambar", tracejada=True,
             rot_xy=(745, 480), ancora="start", rot_linhas=["sem resposta na cadência", "do follow-up"])
    d.aresta([(890, 600), (945, 600), (945, 655), (890, 655)], "ambar", tracejada=True, raio=9,
             rot_xy=(960, 628), ancora="start", rot_linhas=["nova", "tentativa"])
    d.aresta([(570, 640), (310, 640), (310, 750)], "ambar", tracejada=True, raio=14,
             rot_xy=(324, 700), ancora="start", rot_linhas=["esgotaram as", "tentativas"])
    d.aresta([(890, 690), (1490, 690)], "verde", rot_xy=(1190, 668),
             rot_linhas=["o cliente volta e pede o corretor"])

    d.nota(820, 730, 620, [
        "A cadência não é fixa: 120, 1440 e 4320 minutos multiplicados pelo ritmo da",
        "temperatura (quente 0,25 · morno 1 · frio 2), sempre dentro de 08:00–20:00 em SP.",
        "Não há volta automática de Inativo para Qualificando — o retorno do cliente é um",
        "turno novo, roteado pelo que ele disser."], ancora="middle")

    # -------------------------------------------------- nova oportunidade
    d.aresta([(1650, 880), (1650, 1010), (40, 1010), (40, 200), (570, 200), (570, 250)],
             "cinza", tracejada=True, raio=16, rot_xy=(300, 1036), ancora="start",
             rot_linhas=["nova oportunidade (sucessora): o mesmo cliente volta com outra intenção — o lead antigo fica encerrado"])

    d.legenda([("tinta2", "Transição do lead"), ("ambar", "Ausência de resposta"),
               ("verde", "Volta ao atendimento"), ("cinza", "Nova oportunidade")],
              y=1130, tracejados={1, 3})
    d.rodape("jornada do lead")
    return d


if __name__ == "__main__":
    print("\n".join(gerar(montar())))
