"""Diagrama de contexto, versão curta (docs/index.md)."""
from base import Diagrama, gerar


def montar() -> Diagrama:
    d = Diagrama(
        nome="contexto", titulo="Mora em uma olhada",
        subtitulo="Quem fala com quem, do cliente ao banco",
        largura=1840, altura=760,
        alt=("Cliente entra pelo site ou pelo Telegram, os canais publicam no Redis, o agente "
             "consome, fala com o modelo e grava no Postgres; o painel do corretor lê pela API."))

    d.cartao(50, 210, 260, 104, "Cliente", ["Site :5173 ou Telegram"], "pessoa", "azul")
    d.cartao(370, 210, 280, 104, "Canais", ["channels :8001", "telegram-in / out"], "codigo", "azul")
    d.cartao(710, 210, 250, 104, "Redis", ["Streams e lock por lead"], "camadas", "vermelho")
    d.cartao(1020, 180, 320, 164, "Agente", ["services/agent", "Grafo LangGraph:", "supervisor + 9 especialistas"], "faisca", "roxo")
    d.cartao(1420, 150, 370, 104, "Modelos", ["Anthropic · OpenAI · Ollama"], "faisca", "roxo")
    d.cartao(1420, 300, 370, 104, "Postgres + pgvector", ["Leads, imóveis, documentos"], "banco", "cinza")
    d.cartao(370, 520, 280, 104, "Painel do corretor", ["apps/dashboard :5174"], "janela", "azul")
    d.cartao(790, 520, 280, 104, "API REST", ["services/api :8000"], "raio", "cinza")

    d.aresta([(310, 262), (370, 262)], "azul")
    d.aresta([(650, 262), (710, 262)], "azul")
    d.aresta([(960, 246), (1020, 246)], "azul", "inbound", rot_xy=(990, 230))
    d.aresta([(1180, 344), (1180, 400), (835, 400), (835, 314)], "verde",
             rot_xy=(1010, 388), rot_linhas=["resposta neutra"])
    d.aresta([(760, 314), (760, 452), (510, 452), (510, 314)], "verde",
             rot_xy=(636, 440), rot_linhas=["saída dos canais"])
    d.aresta([(1340, 215), (1380, 215), (1380, 202), (1420, 202)], "roxo", raio=8,
             rot_xy=(1400, 176), ancora="end", rot_linhas=["Inferência"])
    d.aresta([(1340, 318), (1380, 318), (1380, 352), (1420, 352)], "cinza", raio=8)
    d.aresta([(650, 572), (790, 572)], "cinza", "HTTP", rot_xy=(720, 556))
    d.aresta([(1070, 572), (1605, 572), (1605, 404)], "cinza", rot_xy=(1330, 556),
             rot_linhas=["Leitura / escrita"])
    d.aresta([(510, 520), (510, 490), (450, 490), (450, 314)], "azul", raio=10,
             rot_xy=(436, 420), ancora="end", rot_linhas=["Tempo real"])

    d.legenda([("azul", "Entrada e tempo real"), ("verde", "Retorno ao cliente"),
               ("roxo", "Modelo"), ("cinza", "Dados")], y=700)
    d.rodape("contexto")
    return d


if __name__ == "__main__":
    print("\n".join(gerar(montar())))
