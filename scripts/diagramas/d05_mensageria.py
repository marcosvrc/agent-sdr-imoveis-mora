"""Tópicos do Redis: quem publica e quem consome (docs/architecture/componentes.md)."""
from base import Diagrama, gerar


def montar() -> Diagrama:
    d = Diagrama(
        nome="mensageria", titulo="Mensageria",
        subtitulo="Um tópico por rota, com produtor e consumidor declarados",
        largura=1960, altura=1010,
        alt="Tabela visual dos tópicos do Redis Streams, com quem publica e quem consome cada um.")

    linhas = [
        ("channels :8001 · telegram-in · scheduler · reativador",
         "mensagem do cliente, follow-up vencido ou aviso de imóvel novo", "sdr:inbound",
         "agent (grafo)", "um turno por vez, com lock por lead", "azul"),
        ("agent · api :8000", "resposta da Mora, ou do corretor em handoff, para o site", "sdr:outbound-web",
         "channels :8001", "empurra no WebSocket aberto", "verde"),
        ("agent · api :8000", "resposta da Mora, ou do corretor em handoff, para o Telegram",
         "sdr:outbound-telegram", "telegram-out", "envia pela Bot API", "verde"),
        ("agent · api :8000", "lead virou qualificado, agendado ou handoff; ou análise pedida no painel",
         "sdr:resumir", "resumidor", "briefing e análise para o corretor", "roxo"),
        ("ingestão do acervo", "todo imóvel ingerido, sem filtro", "sdr:imovel-novo",
         "reativador", "decide quem combina e avisa quem estava adormecido", "roxo"),
        ("agent", "mudou o estágio do lead", "sdr:events",
         "— sem consumidor hoje", "gancho para webhook ou analytics", "cinza"),
    ]
    y0, passo = 196, 116
    for i, (prod, prod_sub, topico, cons, cons_sub, tom) in enumerate(linhas):
        y = y0 + i * passo
        d.cartao(50, y, 520, 74, prod, [prod_sub], None, tom, pequeno=True)
        d.caixa(700, y + 9, 440, 56, topico, "", tom)
        d.cartao(1280, y, 630, 74, cons, [cons_sub], None, tom, pequeno=True)
        d.aresta([(570, y + 37), (700, y + 37)], tom)
        d.aresta([(1140, y + 37), (1280, y + 37)], tom)

    d.add('<text x="50" y="170" class="t-grp">QUEM PUBLICA</text>')
    d.add('<text x="920" y="170" class="t-grp" text-anchor="middle">TÓPICO</text>')
    d.add('<text x="1910" y="170" class="t-grp" text-anchor="end">QUEM CONSOME</text>')

    d.nota(980, 890, 1700, [
        "Follow-up vencido (scheduler) e aviso de imóvel novo (reativador, tipo REATIVACAO) entram em sdr:inbound como um quadro comum, pelo mesmo caminho do cliente.",
        "Cada tópico tem um consumer group; no boot o worker retoma o que ficou pendente na PEL (id 0 e XAUTOCLAIM) — a mensagem entregue no instante de uma queda",
        "não fica sem resposta. O lock por lead é fixo (LOCK_S = 60 s) e renovado a cada 20 s enquanto o turno roda; o pior caso do turno só entra como min_idle do XAUTOCLAIM."])
    d.rodape("mensageria")
    return d


if __name__ == "__main__":
    print("\n".join(gerar(montar())))
