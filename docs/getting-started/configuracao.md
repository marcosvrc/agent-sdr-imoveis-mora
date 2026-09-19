---
title: Configuração e variáveis de ambiente
description: Todas as variáveis SDR_ do Mora, com exemplos seguros e valores padrão.
---

# Configuração e variáveis de ambiente

Todas as variáveis usam o prefixo `SDR_`. Os arquivos de referência são
[`.env.example`](https://github.com/marcosvrc/agent-sdr-imoveis-mora/blob/master/.env.example) (execução
manual, fora do compose) e `local/.env.example` (perfil local, o caminho da entrega).

!!! danger "Nunca use segredos reais no repositório"
    Os valores abaixo são **fictícios**. Não comite tokens, senhas ou chaves. Os dois `.env.example`
    vão para o repositório; os `.env` de verdade, não.

Crie seu arquivo a partir do exemplo:

```bash
cp -n local/.env.example local/.env   # perfil local (docker compose) — `-n` não sobrescreve
cp -n .env.example .env               # execução manual, fora do compose
```

## Referência de variáveis

| Variável | Obrigatória | Exemplo seguro | Descrição |
|---|---|---|---|
| `SDR_ENV` | Não | `dev` | Ambiente lógico. Padrão `dev`. |
| `SDR_PROFILE` | Não | `local` | `local` (padrão) ou `producao`. Não escolhe adaptador — decide **uma** coisa, e é de segurança: se o `dev-token` do painel vale. |
| `SDR_DATABASE_DSN` | **Sim** | `postgresql://sdr:sdr@localhost:5432/sdr` | DSN do Postgres (o mesmo banco do painel e do pgvector). |
| `SDR_LLM_PROVIDER` | Não | `anthropic` | `anthropic` (padrão), `openai` ou `ollama`. |
| `SDR_LLM_PROVIDER_FALLBACK` | Recomendada | `openai` | Provedor de reserva quando o primário falha. Vazio = sem fallback: cada turno vira mensagem de desculpa. Se for de outra família, o modelo é trocado pelo equivalente do papel (ADR-0009). |
| `ANTHROPIC_API_KEY` | Se usar `anthropic` | `sk-ant-…` | Chave da Anthropic. **Sem o prefixo `SDR_`** — é o nome que a biblioteca procura no ambiente. |
| `SDR_MODEL_CONVERSA` | Não | `claude-sonnet-4-5` | Modelo da conversa. |
| `SDR_MODEL_ROTEAMENTO` | Não | `claude-haiku-4-5` | Modelo de roteamento / extração. |
| `SDR_EMBEDDINGS_PROVIDER` | Não | `ollama` | Provedor único: `ollama`. O schema espera 1024 dimensões, que é o que o `bge-m3` dá. |
| `OPENAI_API_KEY` | Se usar `openai` | `sk-…` | Chave da OpenAI. **Sem o prefixo `SDR_`** — é o nome que a biblioteca procura no ambiente, igual à `ANTHROPIC_API_KEY`. Instale o extra: `pip install -e "shared[openai]"`. |
| `SDR_TRANSCRICAO_PROVIDER` | Não | `auto` | Motor de transcrição de áudio: `auto`, `whisper_local` ou `off`. |
| `SDR_WHISPER_MODEL` | Não | `small` | Tamanho do faster-whisper (`tiny`…`large-v3`). |
| `SDR_LLM_TIMEOUT_S` | Não | `45` | Timeout por turno; acima disso o cliente recebe o fallback. |
| `SDR_REDIS_URL` | Não | `redis://localhost:6379/0` | Fila entre a API, os canais e os workers. |
| `SDR_TELEGRAM_BOT_TOKEN` | Não | `000000:exemplo-token` | Token do bot, emitido pelo @BotFather. É o único canal externo. |
| `SDR_TELEGRAM_BOT_USERNAME` | Não | `mora_vertice_bot` | Usuário do bot, para montar o link `t.me/<usuario>`. |
| `SDR_SESSAO_SECRET` | Recomendada | `troque-por-uma-string-aleatoria-longa` | Assina a sessão do chat do site. Sem valor, as sessões caem a cada reinício. |
| `SDR_PAINEL_TOKEN` | Sim (fora do perfil local) | `exemplo-token-painel` | Credencial única do painel: header `Authorization` da API e WebSocket `papel=dashboard`. No perfil local, vazio vira `dev-token`; fora dele, vazio não aceita ninguém. |
| `SDR_CORS_ORIGINS` | Recomendada | `https://app.exemplo.com` | Origens permitidas na API, separadas por vírgula. Vazio = `*` (só em dev). |
| `SDR_GOOGLE_CLIENT_ID` | Não | `exemplo.apps.googleusercontent.com` | OAuth do Google Agenda (opcional). |
| `SDR_GOOGLE_CLIENT_SECRET` | Não | `exemplo-secret` | OAuth do Google Agenda (opcional). |
| `SDR_GOOGLE_REDIRECT_URI` | Não | `http://localhost:8000/calendario/callback` | URI de retorno do OAuth. |

### Menos comuns (têm padrão razoável; mexer só quando precisar)

| Variável | Padrão | Para quê |
| --- | --- | --- |
| `SDR_OLLAMA_URL` | `http://localhost:11434` | Endereço do Ollama (no compose, `http://ollama:11434`). |
| `SDR_OLLAMA_EMBEDDING_MODEL` | `bge-m3` | Modelo de embedding local. Trocar exige regerar os vetores (`make seed`). |
| `SDR_RAG_LEXICO` | *(vazio)* | Liga a fusão léxica (RRF) na busca institucional. Desligada por padrão: no A/B o recall caiu de 31,9% para 29,8%. |
| `SDR_PUBLIC_API_URL` | `http://localhost:8000` | Base para montar URL absoluta de foto nos cards que a Mora envia pelo Telegram. |
| `SDR_FOTOS_DIR` | `data/fotos` | Onde o painel grava foto de imóvel; a API serve essa pasta em `/fotos/...`. |
| `SDR_ANTHROPIC_WORKSPACE_ID` | *(vazio)* | Obrigatório quando a chave é de organização e não de workspace. |
| `SDR_OPENROUTER_API_KEY` | *(vazio)* | **Só para a bancada de avaliação** comparar modelos (ADR-0009). Não usar em produção: põe um terceiro no meio de conversas com dado de cliente. |
| `SDR_LOG_JSON` | *(automático)* | Força log estruturado em JSON (`1`) ou legível (`0`). Sem valor, é JSON fora do perfil local. |
| `SDR_TEST_ALLOW_WIPE` | *(vazio)* | Ignora a trava que impede as suítes de apagar um banco sem "test" no nome. Último recurso. |

### Ponte com o CRM (sistema à parte)

O CRM é um sistema separado, com banco próprio, falado por **MCP sobre HTTP**. São dois segredos
diferentes, e trocá-los um pelo outro dá 401 sem explicação.

| Variável | Onde | Para quê |
| --- | --- | --- |
| `SDR_CRM_URL` | agente | Endpoint do **servidor MCP** (no compose, `http://crm-mcp:8200/mcp`), não a REST. Vazio = ponte desligada e a Mora roda como sempre. |
| `SDR_CRM_TOKEN` | agente | Credencial do agente no servidor MCP. No compose, recebe o valor de `CRM_MCP_TOKEN`. |
| `CRM_MCP_TOKEN` | servidor MCP | O segredo que ele **exige** de quem se conecta. Sem ele, o servidor recusa subir. Gere com `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`. |
| `CRM_API_TOKEN` | servidor MCP | Credencial dele na API REST do CRM. Emita com `make crm-token` — aparece uma vez só. |

## Variáveis dos front-ends (`VITE_*`)

Vite injeta estas variáveis **no momento do build** — não em tempo de execução. Trocar uma delas exige
reconstruir (`npm run build`); num `.env` lido pelos serviços Python elas não têm efeito nenhum.

| Variável | App | Padrão | Para quê |
| --- | --- | --- | --- |
| `VITE_API_URL` | site e painel | `http://localhost:8000` | Base da API REST. |
| `VITE_WS_URL` | site e painel | `ws://localhost:8001/ws` | WebSocket do chat e do tempo real do painel. |
| `VITE_CANAL_URL` | site | `http://localhost:8001` | Serviço de canais (HTTP). |
| `VITE_TELEGRAM_BOT_USERNAME` | site | `mora_vertice_bot` | Monta o link `t.me/<usuario>` do CTA "continuar no Telegram". |
| `VITE_SITE_URL` | site | `https://www.verticeimoveis.exemplo.br` | URL canônica usada no SEO e no JSON-LD das páginas geradas. |
| `VITE_CRM_API` | CRM | `http://localhost:8100` | Base da API REST do CRM, para o painel próprio dele. |

!!! note "O painel não tem provedor de identidade"
    O login do painel é o token estático `SDR_PAINEL_TOKEN`, validado contra a API — não há variável
    `VITE_*` de autenticação. O caminho anterior era um login Cognito via `aws-amplify`, removido junto
    com o resto da AWS.

## Comportamentos padrão úteis

- Sem `SDR_GOOGLE_*`, a Mora usa a grade interna de horários e as visitas continuam sendo marcadas.
- Sem `SDR_TELEGRAM_BOT_TOKEN`, a Mora continua atendendo pelo chat do site e pela CLI (`make cli`).
- Embeddings **não** acompanham o provedor de conversa: os da OpenAI têm 1536 dimensões e o schema
  espera 1024 (bge-m3). Mesmo com `SDR_LLM_PROVIDER=openai`, mantenha `SDR_EMBEDDINGS_PROVIDER=ollama`.
- No perfil local, `SDR_PAINEL_TOKEN` vazio vira `dev-token`.
- `SDR_CORS_ORIGINS` vazio equivale a `*` — aceitável apenas em desenvolvimento.

## Transcrição de áudio

Há um motor só: `faster-whisper` rodando dentro do próprio processo do agente, sem serviço externo e
sem custo por minuto. Exige o agente instalado com o extra `local` (que traz o `faster-whisper`).

- `auto` (padrão) e `whisper_local` dão no mesmo: transcreve localmente.
- `off` desliga a transcrição — ao receber voz, a Mora pede que o cliente escreva.

O `SDR_WHISPER_MODEL` ajusta a qualidade x consumo de CPU/RAM.
Veja o [manual do agente](../user-guide/agente.md#mensagens-de-voz).
