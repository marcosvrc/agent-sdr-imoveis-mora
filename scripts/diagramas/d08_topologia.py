"""Topologia do docker compose (docs/architecture/diagramas.md)."""
from base import Diagrama, gerar


def montar() -> Diagrama:
    d = Diagrama(
        nome="topologia", titulo="Topologia do docker compose",
        subtitulo="Não há um segundo ambiente: isto é o sistema inteiro",
        largura=1960, altura=1060,
        alt="Serviços do docker compose agrupados em front-ends, serviços HTTP, workers e infraestrutura.")

    def bloco(x, y, w, num, titulo, sub, itens, tom) -> float:
        """Altura calculada a partir do número de itens — grupo curto demais escondia cartão."""
        cols = 2 if w > 700 else 1
        linhas = -(-len(itens) // cols)
        h = 62 + linhas * 74 + 8
        d.grupo(x, y, w, h, num, titulo, sub)
        cw = (w - 48 - (cols - 1) * 16) / cols
        for i, (nome, det) in enumerate(itens):
            cx = x + 24 + (i % cols) * (cw + 16)
            cy = y + 62 + (i // cols) * 74
            d.cartao(cx, cy, cw, 62, nome, [det] if det else None, None, tom, pequeno=True)
        return h

    bloco(40, 150, 620, "01", "Front-ends (Vite)", "servidos em modo desenvolvimento", [
        ("web :5173", "site vitrine + widget"),
        ("dashboard :5174", "painel da Mora"),
        ("crm-web :3000", "interface do CRM"),
    ], "azul")

    bloco(700, 150, 620, "02", "Serviços HTTP", "FastAPI e servidor MCP", [
        ("api :8000", "REST da Mora"),
        ("channels :8001", "HTTP + WebSocket"),
        ("crm-api :8100", "REST do CRM"),
        ("crm-mcp :8200", "porta MCP do CRM"),
    ], "verde")

    bloco(1360, 150, 560, "03", "Infraestrutura", "portas do host deslocadas", [
        ("db  5433 → 5432", "Postgres 16 + pgvector · bancos sdr e crm"),
        ("redis  6380 → 6379", "Streams e locks"),
        ("ollama  11435 → 11434", "perfil ollama · modelos locais"),
    ], "cinza")

    bloco(40, 590, 1280, "04", "Workers (sem porta)", "consomem a fila e o relógio", [
        ("agent", "grafo LangGraph · tópico inbound"),
        ("resumidor", "tópico resumir"),
        ("reativador", "tópico imovel-novo"),
        ("scheduler", "laço de 30 s"),
        ("telegram-in", "long polling · getUpdates"),
        ("telegram-out", "envio pela Bot API"),
    ], "roxo")

    bloco(1360, 590, 560, "05", "Opcionais", "sobem por perfil", [
        ("langfuse :3000", "perfil observability · tracing de LLM"),
        ("db-init", "aplica os schemas a cada up"),
    ], "ambar")

    d.nota(980, 920, 1840, [
        "As portas do host (5433, 6380, 11435) evitam colidir com instâncias nativas de Postgres, Redis e Ollama, e mudam por DB_HOST_PORT, REDIS_HOST_PORT e OLLAMA_HOST_PORT.",
        "crm-web e Langfuse publicam a mesma porta 3000 — os dois não sobem juntos. Postgres e Redis são publicados só em 127.0.0.1.",
        "Os serviços Python compartilham uma imagem (local/Dockerfile.python): o que muda entre containers é o comando, não a imagem.",
        "Mudança de schema ou de dependência exige docker compose up -d --build; restart não roda o db-init e o /health/ready reprova dizendo isso."])
    d.rodape("Mora · topologia")
    return d


if __name__ == "__main__":
    print("\n".join(gerar(montar())))
