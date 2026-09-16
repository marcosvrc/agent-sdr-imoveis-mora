---
title: Integrações
description: Provedores de LLM, canais de mensagem, Google Agenda e CRM simulado do Mora.
---

# Integrações

## Provedores de LLM

Selecionáveis por `SDR_LLM_PROVIDER`, com fallback opcional (`SDR_LLM_PROVIDER_FALLBACK`):

| Provedor | Uso | Observação |
|---|---|---|
| `bedrock` | Padrão | Amazon Bedrock (Claude Sonnet / Haiku, Titan Embeddings v2). |
| `anthropic` | Alternativo | API da Anthropic. |
| `ollama` | Local | 100% local, sem custo; embeddings `bge-m3`. |

## Canais de mensagem

| Canal | Estado | Detalhe |
|---|---|---|
| Web (WebSocket) | Ativo | Widget de chat do site (`services/channels/local`, `web`). |
| Telegram | Ativo | Long polling no local (`services/channels/telegram`). Canal externo ativo (ADR-0007). |
| WhatsApp | Desativado | Webhook HMAC, cards e template 24h implementados, mas desligados no compose (ADR-0007). |

## Google Agenda do corretor

Opcional, via `SDR_GOOGLE_CLIENT_ID`, `SDR_GOOGLE_CLIENT_SECRET` e `SDR_GOOGLE_REDIRECT_URI`
(`tools/agenda.py`). Sem essas credenciais, a Mora usa a **grade interna** de horários e as visitas
continuam sendo marcadas — a integração degrada com segurança.

## CRM

O CRM é **simulado** no banco, com o endpoint `/leads/crm/sync`. Não há integração com um sistema de
CRM real (decisão de escopo — ver [Contexto](../overview/contexto.md)).

## Transcrição de áudio (agente multimodal)

Quando o cliente envia uma **mensagem de voz**, o agente transcreve o áudio e trata o texto como
qualquer outra mensagem. O download é roteado pela origem e o motor é escolhido por configuração:

| Origem do áudio | Como baixa | Estado |
|---|---|---|
| Telegram | Bot API (`getFile` + download do arquivo) | Concluída |
| WhatsApp | Graph API da Meta (`media_id` → URL) | Escrita (canal desativado — ADR-0007) |

| Motor de transcrição | Quando | Estado |
|---|---|---|
| `whisper_local` (faster-whisper, in-process) | Perfil local; `auto` no local | Concluída, testada |
| `transcribe` (Amazon Transcribe, S3) | Perfil AWS; `auto` no aws | Escrita, não testada (exige AWS) |

Controle por `SDR_TRANSCRICAO_PROVIDER` (`auto | whisper_local | transcribe | off`) e
`SDR_WHISPER_MODEL`. Veja [Configuração](../getting-started/configuracao.md#transcricao-de-audio) e o
[manual do agente](../user-guide/agente.md#mensagens-de-voz).

!!! note "Entrada de voz tratada como dado não confiável"
    A transcrição entra no prompt dentro do bloco blindado, igual ao texto do cliente — não como
    instrução ao modelo. Veja [Segurança](../quality/seguranca.md). Se a transcrição falhar, a Mora
    pede educadamente para o cliente escrever (degradação segura).

## Bedrock Knowledge Base

RAG gerenciado quando `SDR_KNOWLEDGE_BASE_ID` está definido; caso contrário, o RAG usa pgvector direto
(ADR-0001). O caminho gerenciado não é testado localmente.

!!! warning "Integrações não testadas localmente"
    O Amazon Transcribe (transcrição no perfil AWS), a Bedrock Knowledge Base e os Bedrock Guardrails
    dependem de AWS e não são exercitados no perfil local — no local, a transcrição usa o
    faster-whisper. Veja [Funcionalidades](../overview/funcionalidades.md).
