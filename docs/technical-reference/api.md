---
title: API
description: Referência dos endpoints essenciais da API REST do Mora, autenticação e exemplos.
---

# API

- **URL base (local):** `http://localhost:8000`
- **Especificação completa:** [Swagger (OpenAPI)](openapi.md) — navegável aqui no portal,
  sem precisar subir o backend. Com o ambiente local no ar, o mesmo Swagger fica em
  <http://localhost:8000/docs> e a versão em leitura contínua em <http://localhost:8000/redoc>.
- **Autenticação:** rotas de corretor/admin exigem Cognito JWT (perfil AWS) ou
  `Authorization: Bearer <SDR_PAINEL_TOKEN>` (perfil local). Rotas públicas (`/imoveis`, `/eventos`)
  não exigem autenticação.

!!! note "Fonte da verdade"
    Esta página é um resumo de orientação. A lista completa e sempre atualizada está no
    [Swagger](openapi.md), gerado a partir do código.

## Endpoints essenciais

| Método | Rota | Acesso | Descrição |
|---|---|---|---|
| GET | `/health` | público | Saúde do sistema; 503 quando degradado. |
| GET | `/imoveis` | público | Lista imóveis com filtros (`operacao`, `regiao`, `preco_max`, `quartos`, `limite`). |
| GET | `/imoveis/busca` | público | Busca com filtros adicionais (bairro etc.). |
| GET | `/imoveis/{imovel_id}` | público | Detalhe do imóvel. |
| POST | `/eventos` | público | Registra evento de navegação do site (alimenta o cartão do lead). |
| GET | `/leads` | corretor | Lista leads por estágio / temperatura / corretor. |
| GET | `/leads/{lead_id}` | corretor | Detalhe do lead. |
| POST | `/leads/{lead_id}/analisar` | corretor | Solicita novo briefing / análise (assíncrono). |
| POST | `/handoff/{lead_id}/assumir` | corretor | Corretor assume a conversa. |
| POST | `/handoff/{lead_id}/responder` | corretor | Envia mensagem do corretor pelos canais do lead. |
| GET | `/dashboard/metricas` | corretor | KPIs do período com variação. |
| GET | `/governanca/uso` | admin | Consumo de LLM (tokens, custo, série diária). |
| GET | `/auditoria` | admin | Registro de auditoria. |

## Exemplo

```bash
curl -s "http://localhost:8000/imoveis?operacao=venda&quartos=2&limite=1"
```

```json
[
  {
    "id": "IMOVEL-001",
    "titulo": "Apartamento 2q · Moema",
    "preco": 800000,
    "bairro": "Moema",
    "operacao": "venda"
  }
]
```

Os valores acima são ilustrativos.

## Códigos de status

A API usa os padrões do FastAPI:

- `200 / 201 / 202 / 204` — sucesso.
- `401` — não autenticado.
- `404` — recurso inexistente.
- `503` — no `/health`, quando degradado.
