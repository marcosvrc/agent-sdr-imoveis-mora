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
| GET | `/fotos/{imovel_id}/{nome}` | público | Foto enviada pelo painel, servida de `SDR_FOTOS_DIR`. Fora do Swagger (`include_in_schema=False`). |
| GET | `/acervo/{categoria}/{nome}` | público | Foto do acervo de demonstração, servida de `SDR_FOTOS_ACERVO_DIR`. Fora do Swagger. Nome fora do padrão do indexador dá 404. |

## Canal web (porta 8001)

O chat do site não fala com a API REST: fala com o serviço `channels/local`
(`VITE_CANAL_URL`, padrão `http://localhost:8001`). Essas rotas não entram no Swagger acima.

| Método | Rota | Descrição |
|---|---|---|
| GET | `/health` | 200 só com o barramento (Redis) de pé; 503 caso contrário. |
| POST | `/sessao` | Emite `session_id`, `token` assinado e `expira_em` (12 h). O navegador nunca escolhe o próprio id. Limite de **20 por hora por IP**: acima disso, **429** com `Retry-After`. |
| POST | `/historico` | Corpo `{"session_id", "token"}`. Devolve as últimas 60 mensagens **do canal web** daquela sessão (`de`: `lead` \| `Mora` \| `corretor`, `texto`, `em`, e `opcoes`/`imoveis` nas falas da Mora), para o widget redesenhar a conversa depois de recarregar a página. Token no corpo, nunca na URL; sessão inválida recebe 401 e lista vazia. |
| WS | `/ws?papel=lead` | Conversa do widget; `papel=dashboard` é o espelho do painel. Nos dois, a credencial vai no **primeiro quadro**, nunca na URL (ver abaixo). |

### WebSocket `/ws`

**Autenticação.** O widget manda `{"session_id": "…", "token": "…"}` como primeiro quadro; o painel,
`{"token": "<SDR_PAINEL_TOKEN>"}`. Aceita a credencial, o servidor responde `{"evento": "pronto"}`
(e, para o widget, entrega em seguida as respostas pendentes da sessão, guardadas por até 10 min).
Credencial errada, quadro que não é objeto JSON ou silêncio por **5 s** fecham a conexão: **4401**
para o widget (sessão inventada ou expirada — o widget descarta a sessão e pede outra) e **4403**
para o painel. `id`/`token` na URL são ignorados. `papel` fora de `lead`/`dashboard` fecha com 4400.

**Mensagem do widget.** `{"session_id", "texto", "meta", "ref"}`. Respostas do servidor:
`{"evento": "recebido", "ref"}` quando enfileira; `{"evento": "falha_envio", "ref", "texto"}` quando
recusa — `session_id` diferente do autenticado, `texto` acima de **1 000 caracteres**, limite de
envio atingido ou barramento fora. Do `meta`, só passam ao agente `imovel_origem` (se casar com
`[A-Za-z0-9_-]{1,64}`, o mesmo formato de `POST /eventos`) e `saudacao_exibida: true`; `botao: true`
vira `tipo = botao`; o resto (inclusive `nome`, `telefone`) é descartado.

**Limites.** Quadro acima de **8 KiB** fecha com **1009**; quadro sem `texto` ou JSON inválido fecha
com 1003. Mensagens: **15 por minuto por sessão** e **200 por hora por IP** (somando sessões).
A contagem fica **na memória do processo**: com vários processos/réplicas, cada um conta sozinho
(o teto efetivo multiplica) e reiniciar zera — para escalar, mover para o Redis. Atrás de proxy,
rode o uvicorn com `--proxy-headers` e `--forwarded-allow-ips`, senão todos dividem o IP do proxy.

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

A API usa os padrões do FastAPI. O corpo de erro é `{"detail": ...}` — texto, ou um objeto quando a
tela precisa de mais que a mensagem (como a carteira pendente ao apagar corretor).

- `200 / 201 / 202 / 204` — sucesso.
- `401` — não autenticado.
- `404` — recurso inexistente.
- `409` — conflito com o estado atual: lead já assumido por outro corretor, responder sem ter
  assumido, lead sem canal, corretor com nome repetido ou com carteira aberta (sem `destino`),
  limite de fotos do imóvel.
- `413` — corpo acima do teto: 256 KB em geral, 2,2 MB no `POST /imoveis/{id}/fotos`.
- `422` — validação: parâmetro fora da faixa, campo inválido, modelo sem preço cadastrado.
- `502` — o serviço externo não respondeu o esperado (ex.: sincronização de preços do OpenRouter).
- `503` — no `/health`, quando degradado.
