---
title: Integrações
description: Provedores de LLM, canais de mensagem, Google Agenda e o CRM por MCP do Mora.
---

# Integrações

São cinco, e só cinco: o provedor de LLM, o Ollama, o Telegram, o Google Agenda (opcional) e o CRM
por MCP. Tudo o mais que o sistema usa — Postgres, Redis, transcrição de voz — roda na própria
máquina, dentro do `local/docker-compose.yml`.

## Provedores de LLM

Selecionáveis por `SDR_LLM_PROVIDER`, com reserva opcional (`SDR_LLM_PROVIDER_FALLBACK`), que assume
quando o primário esgota os retries dele:

| Provedor | Uso | Observação |
|---|---|---|
| `anthropic` | Padrão | API da Anthropic (`ANTHROPIC_API_KEY`). |
| `openai` | Alternativo | API da OpenAI (`OPENAI_API_KEY`); modelo trocado pelo equivalente do papel. |
| `ollama` | Local | 100% local, sem custo; qualidade de conversa bem menor. |

Provedor fora dessa lista é recusado no boot com uma mensagem que diz quais valem
(`shared/sdr_shared/ports/factory.py`) — inclusive o provedor hospedado que existia antes, e que foi
removido junto com o resto da infraestrutura em nuvem. Sobre a escolha de falar direto com o
fornecedor do modelo, em vez de um gateway, veja o
[ADR-0009](../adr/0009-gateway-de-llm-litellm-openrouter-ou-nada.md).

## Embeddings

Dois provedores, escolhidos por `SDR_EMBEDDINGS_PROVIDER`, e os dois entregam as **1024
dimensões** que `imoveis.embedding` e `documentos.embedding` declaram:

- **`openai`** (`text-embedding-3-small`, truncado a 1024 pelo parâmetro `dimensions`) — dispensa o
  container do Ollama. Reindexar o acervo inteiro custa frações de centavo.
- **`ollama`** (`bge-m3`) — sem chave e sem custo, ao preço de um container e de ~1 GB de modelo.

Trocar entre eles **exige reindexar** (`make seed` e `make docs-kb`): distância de cosseno entre
vetores de modelos diferentes é ruído com aparência de número. Qual recupera melhor no corpus
deste projeto é medida, não catálogo — `make eval-embeddings` roda os dois lado a lado.

## Ollama

Serviço do compose (`--profile ollama`), em `SDR_OLLAMA_URL`. Faz duas coisas:

- **Embeddings** — `bge-m3`, 1024 dimensões, que é o que o schema espera. É o **único** motor de
  embeddings do projeto; baixe-o com `make ollama-pull`.
- **Conversa**, quando `SDR_LLM_PROVIDER=ollama`.

## Canais de mensagem

| Canal | Estado | Detalhe |
|---|---|---|
| Web (WebSocket) | Ativo | Widget de chat do site, servido por `services/channels/local`. |
| Telegram | Ativo | Long polling (`getUpdates`), sem webhook e sem URL pública (ADR-0007). |
| CLI | Ativo | `make cli` — conversa no terminal, chamando o agente direto, sem canal externo. |

O Telegram é o **único canal externo**. O WhatsApp saiu do código: o webhook da Cloud API exige URL
pública e número de negócio verificado, o que a entrega local não tem
([ADR-0007](../adr/0007-telegram-em-vez-de-whatsapp.md)).

## Google Agenda do corretor

Opcional, via `SDR_GOOGLE_CLIENT_ID`, `SDR_GOOGLE_CLIENT_SECRET` e `SDR_GOOGLE_REDIRECT_URI`. Sem
as duas primeiras, `get_calendario()` devolve a **grade interna** do próprio Postgres e as visitas
continuam sendo marcadas — a integração degrada com segurança.

## CRM

O CRM é um **sistema à parte**, com API REST, banco e painel próprios (`services/crm`, `apps/crm`),
e a Mora fala com ele por **MCP sobre HTTP** — `SDR_CRM_URL` aponta para o servidor MCP (não para a
REST) e `SDR_CRM_TOKEN` é a credencial do agente nele, emitida por `make crm-token`.

Vazio significa ponte desligada: sem `SDR_CRM_URL`, `get_crm()` devolve o adaptador ausente e a Mora
roda sozinha, sem erro. Do lado do CRM, `CRM_MCP_TOKEN` e `CRM_API_TOKEN` são as credenciais do
servidor MCP e da API REST. Veja [decisões](../decisions.md) D-01 e D-02.

## Transcrição de áudio (agente multimodal)

Quando o cliente envia uma **mensagem de voz**, o agente transcreve o áudio e trata o texto como
qualquer outra mensagem (`services/agent/src/agent/tools/transcricao.py`). São dois eixos:

| Origem do áudio | Como baixa | Estado |
|---|---|---|
| Telegram | Bot API (`getFile` + download do arquivo) | Concluída |

| Motor de transcrição | Quando | Estado |
|---|---|---|
| `whisper_local` (faster-whisper, in-process) | `auto` cai nele | Concluída, testada |
| `off` | Desliga | Não transcreve; o cliente recebe o pedido para escrever |

Controle por `SDR_TRANSCRICAO_PROVIDER` (`auto | whisper_local | off`) e `SDR_WHISPER_MODEL`. Não há
serviço externo de transcrição nem cobrança por minuto: o modelo roda no próprio processo. Veja
[Configuração](../getting-started/configuracao.md#transcricao-de-audio) e o
[manual do agente](../user-guide/agente.md#mensagens-de-voz).

!!! note "Entrada de voz tratada como dado não confiável"
    A transcrição entra no prompt dentro do bloco blindado, igual ao texto do cliente — não como
    instrução ao modelo. Veja [Segurança](../quality/seguranca.md). Se a transcrição falhar, a Mora
    pede educadamente para o cliente escrever (degradação segura).

## RAG

Não há serviço gerenciado de RAG. A recuperação é Postgres + pgvector, no mesmo banco do painel
([ADR-0001](../adr/0001-rag-com-postgres-pgvector.md)) — nada sai da máquina além da chamada ao
provedor de LLM.
