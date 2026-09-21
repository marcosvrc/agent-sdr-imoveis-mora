"""Visão macro da arquitetura (README, docs/ARCHITECTURE.md, docs/architecture/index.md)."""
from base import Diagrama, gerar

def montar() -> Diagrama:
    d = Diagrama(
        nome="macro", titulo="Arquitetura — Mora, agente SDR imobiliário",
        subtitulo="Visão macro: entrada, canais, fila, agente, modelos, dados e o CRM à parte",
        largura=2000, altura=1470,
        alt=("Diagrama macro: site e Telegram entram pelos canais, que publicam no Redis; o agente "
             "consome a fila, fala com os modelos, grava no Postgres e espelha no CRM por MCP; "
             "painel e API leem o mesmo banco."))

    # ---------------------------------------------------------------- 01 entrada
    d.grupo(40, 250, 330, 450, "01", "Porta de entrada", "Experiência e aquisição")
    d.cartao(64, 306, 282, 100, "Site / PWA", ["apps/web :5173", "Vitrine + widget de chat"], "janela", "azul")
    d.cartao(64, 540, 282, 100, "Telegram", ["Bot API · long polling", "getUpdates"], "aviao", "azul")
    d.aresta([(205, 406), (205, 540)], "azul", rot_xy=(219, 452), ancora="start",
             rot_linhas=["t.me/bot", "?start=imovel"])

    # ---------------------------------------------------------------- 02 canais
    d.grupo(420, 250, 330, 450, "02", "Canais", "services/channels")
    d.cartao(444, 306, 282, 100, "Channels", [":8001 · HTTP + WebSocket", "Sessão assinada do widget"], "codigo", "azul")
    d.cartao(444, 540, 282, 100, "Telegram I/O", ["telegram-in · long polling", "telegram-out · envio"], "aviao", "azul")

    d.aresta([(346, 356), (444, 356)], "azul", "WS", rot_xy=(395, 344))
    d.aresta([(346, 590), (444, 590)], "azul")

    # ---------------------------------------------------------------- 03 mensageria
    d.add('<text x="800" y="312" class="t-grp">03 MENSAGERIA</text>')
    d.cartao(800, 400, 240, 148, "Redis", ["Streams: inbound,", "outbound-*, resumir,", "events · lock por lead"], "camadas", "vermelho")
    d.aresta([(726, 356), (770, 356), (770, 430), (800, 430)], "azul")
    d.aresta([(726, 590), (770, 590), (770, 518), (800, 518)], "azul")

    # ---------------------------------------------------------------- 04 agente
    d.grupo(1090, 236, 450, 620, "04", "Agente", "services/agent · worker em container")
    d.cartao(1114, 296, 402, 66, "Supervisor", None, "faisca", "roxo", pequeno=True)
    nos = ["Qualificador", "Consultor", "Agendador", "Informações", "Handoff", "Recusa",
           "Follow-up", "Reativador", "Resumidor"]
    for i, nome in enumerate(nos):
        cx = 1114 + (i % 3) * 136
        cy = 392 + (i // 3) * 66
        d.add(f'<rect x="{cx}" y="{cy}" width="126" height="54" rx="9" class="cartao"/>')
        d.add(f'<text x="{cx + 63}" y="{cy + 27}" class="t-sub" text-anchor="middle" '
              f'style="font-weight:600;font-size:12.5px">{nome}</text>')
    d.aresta([(1315, 362), (1315, 386)], "roxo", ponta=False)
    d.add('<text x="1114" y="618" class="t-mini">Regras determinísticas antes do modelo · MAX_SALTOS 4 · histórico podado 40 → 24</text>')
    d.cartao(1114, 646, 402, 86, "Guardrails", ["Porteiro de escopo · prompts blindados", "saída saneada · vazão por lead"], "escudo", "roxo", pequeno=True)
    d.cartao(1114, 748, 402, 86, "Governança", ["Modelo por papel · orçamento", "custo, tokens e latência por nó"], "alvo", "roxo", pequeno=True)

    d.aresta([(1040, 440), (1090, 440)], "azul", "inbound", rot_xy=(1065, 424))
    d.aresta([(1090, 510), (1060, 510), (1060, 548), (920, 548)], "verde",
             rot_xy=(1000, 586), rot_linhas=["resposta", "neutra"])

    # fila → canais (saída)
    d.aresta([(860, 548), (860, 744), (560, 744), (560, 700)], "verde",
             rot_xy=(706, 732), rot_linhas=["saída dos canais"])

    # ---------------------------------------------------------------- 05 modelos
    d.grupo(1590, 236, 370, 372, "05", "Modelos", "Um por papel, trocável pelo painel")
    d.cartao(1614, 296, 322, 128, "LLMs", ["Anthropic · OpenAI · Ollama", "Conversa, roteamento e análise", "Um modelo por papel"], "faisca", "roxo")
    d.cartao(1614, 448, 322, 128, "Embeddings", ["Ollama bge-m3 ou OpenAI", "text-embedding-3-small", "1024 dimensões"], "caixas", "roxo")
    d.aresta([(1540, 330), (1614, 330)], "roxo", "Inferência", rot_xy=(1577, 314))
    d.aresta([(1540, 500), (1614, 500)], "roxo", "Embedding", rot_xy=(1577, 484))

    # ---------------------------------------------------------------- scheduler
    d.cartao(1114, 112, 402, 92, "Scheduler", ["Laço de 30 s: follow-up vencido, amostra de", "saúde, fila do CRM, reindexação do acervo"], "relogio", "verde", pequeno=True)
    d.aresta([(1315, 236), (1315, 204)], "verde", "reagenda o follow-up", rot_xy=(1330, 220), ancora="start")
    d.aresta([(1114, 158), (940, 158), (940, 400)], "verde", rot_xy=(950, 232), ancora="start",
             rot_linhas=["publica o", "turno vencido"])

    # ---------------------------------------------------------------- 06 CRM
    d.grupo(1590, 660, 370, 368, "06", "CRM da imobiliária", "Sistema à parte, com banco próprio")
    d.caixa(1614, 716, 155, 66, "crm-mcp :8200", "18 ferramentas", "verde")
    d.caixa(1781, 716, 155, 66, "apps/crm :3000", "interface do corretor", "azul")
    d.caixa(1614, 820, 322, 56, "crm-api :8100", "", "verde")
    d.caixa(1614, 916, 322, 66, "Banco crm", "mesmo servidor Postgres, banco à parte", "cinza")
    d.aresta([(1691, 782), (1691, 802), (1775, 802), (1775, 820)], "cinza", raio=8)
    d.aresta([(1858, 782), (1858, 802), (1775, 802), (1775, 820)], "cinza", raio=8)
    d.aresta([(1775, 876), (1775, 916)], "cinza")
    d.aresta([(1540, 749), (1614, 749)], "verde", "MCP", rot_xy=(1577, 733))

    # ---------------------------------------------------------------- 07 operação e dados
    d.add('<text x="40" y="1062" class="t-grp">07 OPERAÇÃO E DADOS</text>')
    d.cartao(40, 1096, 330, 104, "Painel da Mora", ["apps/dashboard :5174", "Leads, governança, saúde"], "janela", "azul")
    d.cartao(440, 1096, 310, 104, "API REST", ["services/api :8000", "FastAPI"], "raio", "cinza")
    d.cartao(1090, 1096, 450, 104, "Postgres 16 + pgvector", ["Banco sdr: leads, imóveis, documentos,", "checkpoint do grafo, saúde · busca vetorial"], "banco", "cinza")
    d.cartao(440, 1244, 310, 92, "Fotos", ["data/fotos", "servidas em /fotos"], "imagem", "cinza")

    d.aresta([(370, 1148), (440, 1148)], "cinza", "HTTP", rot_xy=(405, 1132))
    d.aresta([(750, 1148), (1090, 1148)], "cinza", "Leitura / escrita", rot_xy=(920, 1132))
    d.aresta([(595, 1244), (595, 1200)], "cinza", "/fotos", rot_xy=(609, 1224), ancora="start")
    d.aresta([(1315, 856), (1315, 1096)], "cinza", rot_xy=(1329, 950), ancora="start",
             rot_linhas=["Leitura /", "escrita"])
    d.aresta([(205, 1096), (205, 780), (680, 780), (680, 700)], "azul",
             rot_xy=(219, 880), ancora="start", rot_linhas=["Tempo real", "WebSocket do painel"])

    # ---------------------------------------------------------------- legenda
    d.legenda([("azul", "Entrada e tempo real"), ("verde", "Retorno, agenda e CRM"),
               ("roxo", "Processamento de IA"), ("cinza", "Acesso a dados")], y=1400)
    d.rodape("Mora · visão macro")
    return d


if __name__ == "__main__":
    print("\n".join(gerar(montar())))
