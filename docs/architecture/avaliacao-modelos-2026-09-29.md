---
title: Avaliação dos modelos (29/09/2026)
description: Tabelas da matriz de avaliação que embasou a escolha dos modelos, uma por função, com aprovação, custo e latência medidos.
---

# Avaliação dos modelos — 29/09/2026

Resultado de `make eval-matriz` em 29/09/2026, pelo OpenRouter com retenção zero, com **3 repetições por caso**. Custo e latência vêm do registro de uso (`uso_llm`); "falhas técnicas" são chamadas que levantaram exceção. Os candidatos de cada função estão em `services/agent/evals/matriz.json`. A leitura destes números está em [Escolha dos modelos](escolha-de-modelos.md).

## roteamento

Rodada de 2026-09-29 03:25 UTC.

| modelo | roteamento: aprovação | roteamento: via modelo | custo US$ | latência média ms | chamadas | chamadas com erro | falhas técnicas | atendidas por outro modelo |
|---|---|---|---|---|---|---|---|---|
| openai/gpt-6-luna | 58.8% | 42 | 0.0 | 3033 | 42 | 0 | 0 | 0 |
| openai/gpt-oss-120b | 94.1% | 42 | 0.0045 | 599 | 42 | 0 | 0 | 0 |
| nvidia/nemotron-3.5-lightning | 88.2% | 42 | 0.0016 | 1549 | 42 | 0 | 0 | 0 |

## conversa

Rodada de 2026-09-29 01:22 UTC.

| modelo | adversarial: aprovação | adversarial: escape | custo US$ | latência média ms | chamadas | chamadas com erro | falhas técnicas | atendidas por outro modelo |
|---|---|---|---|---|---|---|---|---|
| openai/gpt-6-sol | 72.2% | 0.0% | 0.0495 | 2532 | 27 | 5 | 5 | 0 |
| deepseek/deepseek-v4.1-flash | 100.0% | 0.0% | 0.0088 | 920 | 27 | 0 | 0 | 0 |
| anthropic/claude-sonnet-5 | 100.0% | 0.0% | 0.1426 | 2170 | 27 | 0 | 0 | 0 |

Primeiro erro de cada candidato com chamadas falhando:
- `openai/gpt-6-sol`: {'message': 'openai/gpt-6-sol is temporarily rate-limited upstream. Please retry shortly, or add your own key to accumulate your rate limits: https://openrouter.ai/settings/integrations', 'code': 429, 'metadata': {'error_type': 'rate_limit_exceeded'}}

## extracao

Rodada de 2026-09-29 00:27 UTC.

| modelo | extracao: aprovação | extracao: acerto por campo | extracao: inventados | coerencia: aprovação | custo US$ | latência média ms | chamadas | falhas técnicas |
|---|---|---|---|---|---|---|---|---|
| openai/gpt-6-luna | 88.0% | 95.2% | 3 | 100.0% | 0.0427 | 1824 | 132 | 0 |
| deepseek/deepseek-v4.1-flash | 68.0% | 94.4% | 23 | 100.0% | 0.0383 | 1202 | 132 | 0 |
| openai/gpt-oss-120b | 8.0% | 11.9% | 6 | 0.0% | 0.0 | 60 | 132 | 0 |
| anthropic/claude-sonnet-5 | 88.0% | 95.2% | 3 | 100.0% | 1.206 | 3679 | 132 | 0 |

## informacoes

Rodada de 2026-09-29 01:03 UTC.

| modelo | informacoes: aprovação | informacoes: cita fonte | informacoes: inventou | informacoes: sem base ok | custo US$ | latência média ms | chamadas | chamadas com erro | falhas técnicas | atendidas por outro modelo |
|---|---|---|---|---|---|---|---|---|---|---|
| openai/gpt-6-sol | 13.3% | 100.0% | 6 | 100.0% | 0.0847 | 2737 | 45 | 15 | 11 | 0 |
| deepseek/deepseek-v4.1-flash | 86.7% | 100.0% | 6 | 100.0% | 0.0099 | 935 | 45 | 0 | 0 | 0 |
| openai/gpt-6-luna | 80.0% | 100.0% | 9 | 100.0% | 0.0064 | 1724 | 45 | 0 | 0 | 0 |

Primeiro erro de cada candidato com chamadas falhando:
- `openai/gpt-6-sol`: {'message': 'openai/gpt-6-sol is temporarily rate-limited upstream. Please retry shortly, or add your own key to accumulate your rate limits: https://openrouter.ai/settings/integrations', 'code': 429, 'metadata': {'error_type': 'rate_limit_exceeded'}}

## analise

Rodada de 2026-09-29 00:12 UTC.

| modelo | analise: aprovação | analise: estruturada | custo US$ | latência média ms | chamadas | falhas técnicas |
|---|---|---|---|---|---|---|
| z-ai/glm-5.3-flash | 66.7% | 66.7% | 0.0129 | 38999 | 12 | 0 |
| deepseek/deepseek-v4.1-flash | 100.0% | 100.0% | 0.0082 | 8744 | 12 | 0 |
| openai/gpt-6-sol | 50.0% | 50.0% | 0.0431 | 3352 | 10 | 2 |
| anthropic/claude-opus-5.5 | 100.0% | 100.0% | 0.3138 | 10992 | 12 | 0 |
