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
| `SDR_DATABASE_DSN` | **Sim** | `postgresql://sdr:sdr@localhost:5433/sdr` | DSN do Postgres (o mesmo banco do painel e do pgvector). No compose já vem preenchido (`db:5432`); do host, o Postgres do compose fica em `5433`. |
| `SDR_LLM_PROVIDER` | Não | `anthropic` | `anthropic` (padrão), `openai`, `ollama` ou `openrouter` (ADR-0016). |
| `SDR_LLM_PROVIDER_FALLBACK` | Recomendada | `openai` | Provedor de reserva quando o primário falha. Vazio = sem fallback: cada turno vira mensagem de desculpa. Se for de outra família, o modelo é trocado pelo equivalente do papel (ADR-0009). |
| `ANTHROPIC_API_KEY` | Se usar `anthropic` | `sk-ant-…` | Chave da Anthropic. **Sem o prefixo `SDR_`** — é o nome que a biblioteca procura no ambiente. |
| `SDR_MODEL_CONVERSA` | Não | `claude-sonnet-4-5` | Modelo da conversa. |
| `SDR_MODEL_ROTEAMENTO` | Não | `claude-haiku-4-5` | Modelo do supervisor (e da extração, se ela não tiver o seu). |
| `SDR_MODEL_EXTRACAO` | Não | *(vazio → roteamento)* | Modelo da extração do cartão (ADR-0016). |
| `SDR_MODEL_INFORMACOES` | Não | *(vazio → conversa)* | Modelo do RAG institucional. |
| `SDR_MODEL_ANALISE` | Não | *(vazio → conversa)* | Modelo do briefing e da análise. |
| `SDR_EMBEDDINGS_PROVIDER` | Não | `ollama` | `ollama` (bge-m3), `openai` ou `openrouter` (text-embedding-3-small reduzido a 1024). O schema espera 1024 dimensões. Trocar de modelo exige reindexar; trocar só o caminho do mesmo modelo (OpenAI ↔ OpenRouter), não. |
| `SDR_EMBEDDINGS_MODEL` | Não | `text-embedding-3-small` | Modelo de embedding para `openai` e `openrouter`. Pelo OpenRouter, sem fornecedor no ID vira `openai/…`. |
| `OPENAI_API_KEY` | Se usar `openai` | `sk-…` | Chave da OpenAI. **Sem o prefixo `SDR_`** — é o nome que a biblioteca procura no ambiente, igual à `ANTHROPIC_API_KEY`. Instale o extra: `pip install -e "shared[openai]"`. |
| `SDR_TRANSCRICAO_PROVIDER` | Não | `auto` | Motor de transcrição de áudio: `auto`, `whisper_local` ou `off`. |
| `SDR_WHISPER_MODEL` | Não | `small` | Tamanho do faster-whisper (`tiny`…`large-v3`). |
| `SDR_PROMPT_CACHE` | Não | `true` | Marca o prefixo do prompt para o cache do provedor (só Anthropic). Ligado é seguro: abaixo do mínimo de tokens a marca é ignorada sem erro. Se engatou, aparece em Governança → Leitura de cache. |
| `SDR_LLM_TIMEOUT_S` | Não | `45` | Timeout por chamada ao modelo (1 tentativa extra por provedor). O pior caso de um turno e a validade do lock por lead derivam daqui. |
| `SDR_DB_POOL_MAX` | Não | `4` | Conexões do pool **por processo**. O compose sobe para `12` na API, que atende painel, site e canal ao mesmo tempo. |
| `SDR_REDIS_URL` | Não | `redis://localhost:6379/0` | Fila entre a API, os canais e os workers. |
| `SDR_TELEGRAM_BOT_TOKEN` | Não | `000000:exemplo-token` | Token do bot, emitido pelo @BotFather. É o único canal externo. |
| `SDR_TELEGRAM_BOT_USERNAME` | Não | `mora_vertice_bot` | Usuário do bot, para montar o link `t.me/<usuario>`. |
| `SDR_CHAT_NOVA_CONVERSA` | Não | `false` | Modo de teste do chat do site: `true` faz cada carregamento da página começar um atendimento novo e mostra o botão "Nova conversa". Aplicar com `docker compose up -d web`. |
| `SDR_SESSAO_SECRET` | Recomendada | *(gere: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`)* | Segredo do qual saem três chaves, uma por finalidade (HMAC-SHA256 com os rótulos `sessao`, `oauth`, `cofre`): assina a sessão do chat do site, assina o `state` do OAuth do Google Agenda e cifra o refresh token do calendário no banco. **Os serviços recusam subir com o valor de exemplo que já esteve nos `.env.example`** (era público); `scripts/check_env.py` acusa o mesmo. **Vazio**: cada processo gera uma chave aleatória (com aviso no log) — as sessões de chat caem a cada reinício, o link de conexão da agenda só vale no processo que o emitiu e o refresh token fica em claro (com aviso). **Trocar o valor invalida as credenciais de calendário já guardadas** (exceção: as cifradas com o valor de exemplo continuam legíveis e são regravadas com o novo) e as sessões de chat abertas. |
| `SDR_PAINEL_TOKEN` | Sim (fora do perfil local) | `exemplo-token-painel` | Credencial única do painel: header `Authorization` da API e WebSocket `papel=dashboard`. No perfil local, vazio vira `dev-token`; fora dele, vazio não aceita ninguém. Com o `dev-token` valendo, a API e o canal registram um aviso ao subir, e `check_env.py` também avisa. |
| `SDR_CORS_ORIGINS` | Recomendada | `https://app.exemplo.com` | Origens permitidas na API, separadas por vírgula. Vazio: no perfil local, só os front-ends do compose (5173, 5174, 3000); fora dele, nenhuma origem externa. |
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
| `SDR_FOTOS_ACERVO_DIR` | `data/fotos-acervo` | Fotos do acervo de demonstração, servidas em `/acervo/...`. Prefixo separado de propósito: `/fotos/%` é o que marca foto do painel na precedência do upsert (ADR-0015). |
| `SDR_ANTHROPIC_WORKSPACE_ID` | *(vazio)* | Obrigatório quando a chave é de organização e não de workspace. |
| `SDR_OPENROUTER_API_KEY` | *(vazio)* | Chave do OpenRouter, quando ele atende algum papel (ADR-0016). |
| `SDR_OPENROUTER_ZDR` | `true` | Retenção zero em toda requisição ao OpenRouter. Desligar só na bancada, com dataset sintético: sem ela, o texto do cliente pode ir para endpoints que o guardam. |
| `SDR_OPENROUTER_URL` | `https://openrouter.ai/api/v1` | Base da API do OpenRouter (os testes apontam para um servidor falso). |
| `SDR_EMBEDDINGS_DIMENSOES` | `1024` | Dimensão dos vetores; tem de casar com o `vector(N)` de `shared/sdr_shared/db/schema.sql`. |
| `SDR_ACERVO_REFRESH_S` | `900` | De quanto em quanto tempo (segundos) o scheduler traz o acervo do CRM de volta ao índice; `0` desliga. O valor salvo no painel (Configurações → Operação) tem precedência. |
| `DB_HOST_PORT` / `REDIS_HOST_PORT` / `OLLAMA_HOST_PORT` | `5433` / `6380` / `11435` | Portas publicadas **no host** pelo compose, para acesso de fora dele; os containers usam sempre as portas internas. |
| `HOST_BIND` | `127.0.0.1` | Endereço do host em que o compose publica API, canais, CRM e os três Vite. `0.0.0.0` abre para a rede — defina antes um `SDR_PAINEL_TOKEN` forte. Postgres, Redis, Ollama e Langfuse ficam no loopback sempre. Ver [Executando com Docker](docker.md#acesso-de-outro-aparelho-da-rede). |
| `CONTAINER_USER` | `mora` | Usuário dos containers Python. `root` é a válvula de escape se um bind mount recusar escrita (ver [Executando com Docker](docker.md#usuario-dos-containers-python)). |
| `LANGFUSE_HOST_PORT` / `LANGFUSE_NEXTAUTH_SECRET` / `LANGFUSE_SALT` | `3001` / padrão de dev / padrão de dev | Só com `--profile observability`. Nenhum código envia trace ao Langfuse ainda. |
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
| `CRM_FOTOS_BASE_URL` | seed do CRM | Base para transformar a foto relativa do acervo (`/acervo/...`) em URL absoluta, que é o que a coluna `property_photos.url` aceita. Padrão: `SDR_PUBLIC_API_URL` ou `http://localhost:8000`. |

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
- Embeddings **não** acompanham o provedor de conversa: são escolhidos em `SDR_EMBEDDINGS_PROVIDER`.
  O `text-embedding-3-small` nasce com 1536 dimensões e o adaptador pede 1024 (`dimensions`); vetor
  de outro tamanho é recusado antes de gravar. Para usar só o OpenRouter, `SDR_EMBEDDINGS_PROVIDER=openrouter`
  dispensa a `OPENAI_API_KEY` sem reindexar.
- No perfil local, `SDR_PAINEL_TOKEN` vazio vira `dev-token` (com aviso no log da API e do canal).
- `SDR_SESSAO_SECRET` vazio: chave aleatória por processo, com aviso; com o valor de exemplo do
  repositório, nenhum serviço sobe.
- `SDR_CORS_ORIGINS` vazio aceita só os front-ends do compose no perfil local, e nenhuma origem fora dele.

## Transcrição de áudio

Há um motor só: `faster-whisper` rodando dentro do próprio processo do agente, sem serviço externo e
sem custo por minuto. Exige o agente instalado com o extra `local` (que traz o `faster-whisper`).

- `auto` (padrão) e `whisper_local` dão no mesmo: transcreve localmente.
- `off` desliga a transcrição — ao receber voz, a Mora pede que o cliente escreva.

O `SDR_WHISPER_MODEL` ajusta a qualidade x consumo de CPU/RAM.
Veja o [manual do agente](../user-guide/agente.md#mensagens-de-voz).
