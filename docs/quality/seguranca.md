---
title: Segurança e privacidade
description: Controles de segurança do Mora classificados por estado, riscos conhecidos e aspectos de LGPD.
---

# Segurança e privacidade

Legenda de estado: **Implementado**, **Parcial**, **Recomendado**.

!!! danger "Isto é uma POC"
    A existência de um controle não implica que o sistema seja seguro para produção.

## Controles

| Controle | Estado | Detalhe |
|---|---|---|
| Autenticação do painel | Implementado | Token estático `SDR_PAINEL_TOKEN`, comparado em tempo constante; **fail-closed** fora do perfil local — ADR-0008 |
| Autorização por área | Implementado | Rotas separadas (público / corretor / admin / operação) |
| Estado OAuth assinado (HMAC) | Implementado | `seguranca/oauth.py` protege o retorno do Google Agenda |
| Sessão assinada do chat do site | Implementado | `SDR_SESSAO_SECRET` impede sequestro de sessão |
| Sanitização de entrada | Implementado | `MensagemNormalizada`: trunca tamanho, remove controles / invisíveis |
| Guardrail de escopo (prompt injection) | Implementado | `guardrails/escopo.py`: recusa reprogramação, homóglifos e off-topic sem chamar o LLM |
| Blindagem de prompt | Implementado | Persona + cabeçalho de regras; texto do cliente em bloco com sentinela aleatória |
| Saneamento de saída | Implementado | `guardrails/saida.py`: descarta vazamento de instrução, mascara PII (CPF / cartão), remove tags / código / links |
| Injeção indireta via RAG | Implementado | Descrição de imóvel neutralizada antes de entrar no prompt |
| Rate limiting | Implementado | Por lead (rajada e hora) — `guardrails/vazao.py` |
| Auditoria | Implementado | Middleware registra tudo que altera o sistema |
| CORS | Implementado | `SDR_CORS_ORIGINS` (vazio = `*`, só em dev) |
| Gerenciamento de secrets | Parcial | Só `.env` (`local/.env`, fora do versionamento). Não há cofre de segredos — a entrega roda na máquina de quem avalia |
| Criptografia em trânsito | Parcial | Tudo é HTTP/WS em `localhost`; nada está exposto na rede. Chamadas de saída (LLM, Telegram, Google) são HTTPS |
| Tratamento de PII / LGPD | Parcial | Mascaramento na saída; página de privacidade no site. Política de retenção formal: recomendada |
| Análise de dependências | Recomendado | Não há varredura automatizada no CI |
| Moderação do provedor de LLM | Recomendado | Só os guardrails próprios do projeto; nenhum filtro do fornecedor é configurado |

PII = Personally Identifiable Information (informação pessoal identificável).
LGPD = Lei Geral de Proteção de Dados.

## Proteção do texto enviado ao LLM

O texto do cliente **nunca** é concatenado cru no prompt: entra em um bloco delimitado por sentinela
aleatória, com um cabeçalho de blindagem que instrui o modelo a tratá-lo como dado, não instrução. A
saída passa por saneamento antes de virar mensagem. Veja [Fluxo do agente e LLM](../architecture/fluxo-agente.md).

## Riscos conhecidos

- Rate limiting é **por processo** (não distribuído entre múltiplos workers).
- Transcrição de áudio: já é tratada como **entrada não confiável** (entra blindada, como o texto do
  cliente), mas **não há teste adversarial específico** de injeção via áudio transcrito.
- Não há TLS: a entrega é local e nada é servido fora da máquina. Publicar isto em rede exigiria um
  proxy com certificado na frente, que não existe no repositório.

Os comentários em `services/agent/src/agent/guardrails/` detalham cada ponto.

## Dados pessoais e LGPD

Há mascaramento de PII na saída e uma página de privacidade no site. Uma **política formal de retenção
e exclusão** de dados é recomendada e ainda não existe (ver [Pendências](../project/pendencias.md)).
