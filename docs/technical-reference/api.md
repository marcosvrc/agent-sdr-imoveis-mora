---
title: API
description: Referência dos endpoints essenciais da API REST do Mora, autenticação e exemplos.
---

# API

- **URL base (local):** `http://localhost:8000`
- **Especificação completa:** [Swagger (OpenAPI)](openapi.md) — navegável aqui no portal,
  sem precisar subir o backend. Com o ambiente local no ar, o mesmo Swagger fica em
  <http://localhost:8000/docs> e a versão em leitura contínua em <http://localhost:8000/redoc>.
- **Autenticação:** rotas de corretor/admin exigem `Authorization: Bearer <SDR_PAINEL_TOKEN>`.
  No perfil local, sem token configurado, vale `dev-token`; fora dele, sem segredo configurado nada
  é aceito. Rotas públicas (`/imoveis`, `/eventos`) não exigem autenticação. Veja
  [Segurança](../quality/seguranca.md).

!!! note "Fonte da verdade"
    Esta página é um resumo de orientação. A lista completa e sempre atualizada está no
    [Swagger](openapi.md), gerado a partir do código.

## Endpoints essenciais

| Método | Rota | Acesso | Descrição |
|---|---|---|---|
| GET | `/health` | público | Saúde do sistema; 503 quando degradado. |
| GET | `/imoveis` | público | Lista imóveis com filtros (`operacao`, `regiao`, `preco_max`, `quartos`, `limite` até 400), sem paginação — é a rota do chat. |
| GET | `/imoveis/busca` | público | Catálogo paginado da vitrine: `bairro`, `tipo`, `segmento` (`residencial` \| `comercial`), faixas de preço, quartos, suítes, vagas, área, `texto`, `ordenar`, `limite` (até 60) e `offset`. |
| GET | `/imoveis/{imovel_id}` | público | Detalhe do imóvel. |
| POST | `/eventos` | público | Registra evento de navegação do site (alimenta o cartão do lead). |
| GET | `/leads` | corretor | Lista leads por estágio / temperatura / corretor. |
| GET | `/leads/{lead_id}` | corretor | Detalhe do lead. |
| POST | `/leads/{lead_id}/analisar` | corretor | Solicita novo briefing / análise (assíncrono). |
| POST | `/handoff/{lead_id}/assumir` | corretor | Corretor assume a conversa. |
| POST | `/handoff/{lead_id}/responder` | corretor | Envia mensagem do corretor pelos canais do lead. |
| GET | `/dashboard/metricas` | corretor | KPIs do período com variação. |
| GET | `/governanca/uso` | admin | Consumo de LLM (tokens, custo, série diária). |
| GET | `/config/modelos/comparacao` | admin | Custo contrafactual e latência dos modelos por papel. |
| POST | `/config/modelos/openrouter/sincronizar` | admin | Traz do catálogo do OpenRouter o preço dos modelos informados (`{"modelos": ["google/…"]}`, até 50, formato `fornecedor/modelo`); devolve `gravados` e `nao_encontrados` (502 se nenhum preço veio). |
| POST | `/config/modelos/testar` | admin | Testa um modelo antes de salvá-lo. |
| GET | `/auditoria` | admin | Registro de auditoria. |

## Canal web (porta 8001)

O chat do site não fala com a API REST: fala com o serviço `channels/local`
(`VITE_CANAL_URL`, padrão `http://localhost:8001`). Essas rotas não entram no Swagger acima.

| Método | Rota | Descrição |
|---|---|---|
| GET | `/health` | 200 só com o barramento (Redis) de pé; 503 caso contrário. |
| POST | `/sessao` | Emite `session_id`, `token` assinado e `expira_em` (12 h). O navegador nunca escolhe o próprio id. |
| POST | `/historico` | Corpo `{"session_id", "token"}`. Devolve as últimas 60 mensagens **do canal web** daquela sessão (`de`: `lead` \| `Mora` \| `corretor`, `texto`, `em`, e `opcoes`/`imoveis` nas falas da Mora), para o widget redesenhar a conversa depois de recarregar a página. Token no corpo, nunca na URL; sessão inválida recebe 401 e lista vazia. |
| WS | `/ws?papel=lead&id=…&token=…` | Conversa do widget; `papel=dashboard` é o espelho do painel (credencial no primeiro quadro). |

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
