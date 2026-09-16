---
title: Configuração e variáveis de ambiente
description: Todas as variáveis SDR_ do Mora, com exemplos seguros e valores padrão.
---

# Configuração e variáveis de ambiente

Todas as variáveis usam o prefixo `SDR_`. Os arquivos de referência são
[`.env.example`](https://github.com/marcosvrc/agent-sdr-imoveis-mora/blob/master/.env.example) (execução manual /
deploy) e `local/.env.example` (perfil local).

!!! danger "Nunca use segredos reais no repositório"
    Os valores abaixo são **fictícios**. Não comite tokens, senhas ou chaves. Em produção, o perfil AWS
    usa o AWS Secrets Manager.

Crie seu arquivo a partir do exemplo:

```bash
cp .env.example .env                  # execução manual / deploy
cp local/.env.example local/.env      # perfil local (docker compose)
```

## Referência de variáveis

| Variável | Obrigatória | Exemplo seguro | Descrição |
|---|---|---|---|
| `SDR_ENV` | Não | `dev` | Ambiente lógico. Padrão `dev`. |
| `SDR_PROFILE` | Não | `local` | `aws` (padrão) ou `local`; decide fila, scheduler e hospedagem. |
| `SDR_AWS_REGION` | Não | `us-east-1` | Região AWS. |
| `SDR_DATABASE_DSN` | **Sim** | `postgresql://sdr:sdr@localhost:5432/sdr` | DSN do Postgres. |
| `SDR_LLM_PROVIDER` | Não | `bedrock` | `bedrock`, `anthropic`, `openai` ou `ollama`. Padrão `bedrock`. |
| `SDR_LLM_PROVIDER_FALLBACK` | Recomendada | `openai` | Provedor de reserva quando o primário falha. Vazio = sem fallback: cada turno vira mensagem de desculpa. Se for de outra família, o modelo é trocado pelo equivalente do papel (ADR-0009). |
| `SDR_MODEL_CONVERSA` | Não | `anthropic.claude-sonnet-4-5` | Modelo da conversa. |
| `SDR_MODEL_ROTEAMENTO` | Não | `anthropic.claude-haiku-4-5` | Modelo de roteamento / extração. |
| `SDR_EMBEDDINGS_PROVIDER` | Não | `bedrock` | `bedrock` ou `ollama`. |
| `SDR_KNOWLEDGE_BASE_ID` | Não | *(vazio)* | ID da Knowledge Base; vazio = fallback pgvector direto. |
| `OPENAI_API_KEY` | Se usar `openai` | `sk-…` | Chave da OpenAI. **Sem o prefixo `SDR_`** — é o nome que a biblioteca procura no ambiente, igual à `ANTHROPIC_API_KEY`. Instale o extra: `pip install -e "shared[openai]"`. |
| `SDR_TRANSCRICAO_PROVIDER` | Não | `auto` | Motor de transcrição de áudio: `auto`, `whisper_local`, `transcribe` ou `off`. |
| `SDR_WHISPER_MODEL` | Não | `small` | Tamanho do faster-whisper (`tiny`…`large-v3`) no motor local. |
| `SDR_AUDIO_BUCKET` | Não | *(vazio)* | Bucket S3 usado pelo Amazon Transcribe (perfil AWS). |
| `SDR_LLM_TIMEOUT_S` | Não | `45` | Timeout por turno; acima disso o cliente recebe o fallback. |
| `SDR_REDIS_URL` | Não (local) | `redis://localhost:6379/0` | Fila do perfil local. |
| `SDR_TELEGRAM_BOT_TOKEN` | Não | `000000:exemplo-token` | Token do bot (canal ativo no local). |
| `SDR_TELEGRAM_BOT_USERNAME` | Não | `mora_vertice_bot` | Usuário do bot, para montar o link `t.me/<usuario>`. |
| `SDR_WHATSAPP_PHONE_NUMBER_ID` | Não | `000000000000000` | ID do número (canal WhatsApp, desativado). |
| `SDR_WHATSAPP_TOKEN` | Não | `EAAB...exemplo` | Token da Meta Cloud API. |
| `SDR_WHATSAPP_APP_SECRET` | Não | `exemplo-app-secret` | Segredo para validar HMAC do webhook. |
| `SDR_WHATSAPP_VERIFY_TOKEN` | Não | `sdr-verify` | Token de verificação do webhook. Padrão `sdr-verify`. |
| `SDR_SESSAO_SECRET` | Recomendada | `troque-por-uma-string-aleatoria-longa` | Assina a sessão do chat do site. Sem valor, as sessões caem a cada reinício. |
| `SDR_PAINEL_TOKEN` | Sim (fora do local) | `exemplo-token-painel` | Credencial do painel fora do API Gateway (WebSocket). No local vazio vira `dev-token`. |
| `SDR_CORS_ORIGINS` | Recomendada (produção) | `https://app.exemplo.com` | Origens permitidas na API, separadas por vírgula. Vazio = `*` (só em dev). |
| `SDR_GOOGLE_CLIENT_ID` | Não | `exemplo.apps.googleusercontent.com` | OAuth do Google Agenda (opcional). |
| `SDR_GOOGLE_CLIENT_SECRET` | Não | `exemplo-secret` | OAuth do Google Agenda (opcional). |
| `SDR_GOOGLE_REDIRECT_URI` | Não | `http://localhost:8000/calendario/callback` | URI de retorno do OAuth. |

### Menos comuns (têm padrão razoável; mexer só quando precisar)

| Variável | Padrão | Para quê |
| --- | --- | --- |
| `SDR_MODEL_EMBEDDING` | `amazon.titan-embed-text-v2:0` | Modelo de embedding no Bedrock. |
| `SDR_OLLAMA_URL` | `http://localhost:11434` | Endereço do Ollama (no compose, `http://ollama:11434`). |
| `SDR_OLLAMA_EMBEDDING_MODEL` | `bge-m3` | Modelo de embedding local. Trocar exige regerar os vetores (`make seed`). |
| `SDR_GUARDRAIL_ID` | *(vazio)* | Guardrail do Bedrock (perfil AWS). Vazio = só os guardrails do próprio código. |
| `SDR_EVENTBUS_NAME` | `sdr-events` | Barramento de eventos de domínio (perfil AWS). |
| `SDR_SCHEDULER_GROUP` | `sdr-followup` | Grupo do EventBridge Scheduler que dispara follow-up (perfil AWS). |
| `SDR_PUBLIC_API_URL` | `http://localhost:8000` | Base para montar URL absoluta de foto nos cards que saem por Telegram/WhatsApp. |
| `SDR_FOTOS_DIR` | `data/fotos` | Onde o painel grava foto de imóvel no perfil local. |
| `SDR_ANTHROPIC_WORKSPACE_ID` | *(vazio)* | Obrigatório quando a chave é de organização e não de workspace. |
| `SDR_OPENROUTER_API_KEY` | *(vazio)* | **Só para a bancada de avaliação** comparar modelos (ADR-0009). Não usar em produção: põe um terceiro no meio de conversas com dado de cliente. |
| `SDR_LOG_JSON` | *(automático)* | Força log estruturado em JSON (`1`) ou legível (`0`). Sem valor, é JSON fora do perfil local. |
| `SDR_TEST_ALLOW_WIPE` | *(vazio)* | Ignora a trava que impede as suítes de apagar um banco sem "test" no nome. Último recurso. |

## Variáveis dos front-ends (`VITE_*`)

Vite injeta estas variáveis **no momento do build** — não em tempo de execução. Trocar uma delas exige
reconstruir (`npm run build`) e republicar; num `.env` do servidor elas não têm efeito nenhum.

| Variável | App | Padrão | Para quê |
| --- | --- | --- | --- |
| `VITE_API_URL` | site e painel | `http://localhost:8000` | Base da API REST. |
| `VITE_WS_URL` | site e painel | `ws://localhost:8001` | WebSocket do chat e do tempo real do painel. |
| `VITE_CANAL_URL` | site | `http://localhost:8001` | Serviço de canais (HTTP). |
| `VITE_TELEGRAM_BOT_USERNAME` | site | *(vazio)* | Monta o link `t.me/<usuario>` do CTA "continuar no Telegram". Vazio = o botão não aparece. |
| `VITE_SITE_URL` | site | `http://localhost:5173` | URL canônica usada no SEO e no JSON-LD das páginas geradas. |
| `VITE_COGNITO_USER_POOL_ID` | painel | *(vazio)* | Pool do Cognito. |
| `VITE_COGNITO_CLIENT_ID` | painel | *(vazio)* | App client do Cognito. |

!!! warning "Sem as duas do Cognito, o painel publicado entra em modo local"
    O painel só exige login do Cognito quando `VITE_COGNITO_USER_POOL_ID` **e** `VITE_COGNITO_CLIENT_ID`
    estão presentes no build. Sem elas ele cai no modo de desenvolvimento (token estático) **sem avisar** —
    e como o `FrontendStack` publica o `dist/` construído na sua máquina, é no seu terminal que elas
    precisam estar ao rodar `npm run build`, não no ambiente da AWS. Confira o `index.html` publicado
    antes de considerar o deploy pronto.

## Comportamentos padrão úteis

- Sem `SDR_GOOGLE_*`, a Mora usa a grade interna de horários e as visitas continuam sendo marcadas.
- Sem `SDR_KNOWLEDGE_BASE_ID`, o RAG usa **pgvector direto** (o caminho testado localmente).
- Embeddings **não** acompanham o provedor de conversa: os da OpenAI têm 1536 dimensões e o schema
  espera 1024 (bge-m3). Com `openai`, mantenha `SDR_EMBEDDINGS_PROVIDER=ollama`.
- No perfil local, `SDR_PAINEL_TOKEN` vazio vira `dev-token`.
- `SDR_CORS_ORIGINS` vazio equivale a `*` — aceitável apenas em desenvolvimento.

## Transcrição de áudio

Com `SDR_TRANSCRICAO_PROVIDER=auto` (padrão), o motor é escolhido pelo perfil:

- **Perfil local** → `whisper_local` (faster-whisper rodando in-process, sem AWS e sem custo). Exige o
  agente instalado com o extra `local` (que traz o `faster-whisper`).
- **Perfil AWS** → `transcribe` (Amazon Transcribe; usa `SDR_AUDIO_BUCKET`).

Você pode forçar um motor (`whisper_local` ou `transcribe`) ou desligar a transcrição com `off` — nesse
caso, ao receber voz, a Mora pede que o cliente escreva. O `SDR_WHISPER_MODEL` ajusta a qualidade x
consumo de CPU/RAM do motor local. Veja o [manual do agente](../user-guide/agente.md#mensagens-de-voz).
