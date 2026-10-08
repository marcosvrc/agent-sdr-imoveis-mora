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
| Autenticação do painel | Implementado | Token estático `SDR_PAINEL_TOKEN`, comparado em tempo constante; **fail-closed** fora do perfil local — ADR-0008. No perfil local sem token, o `dev-token` (público) vale: a API e o canal **avisam no log ao subir** e `scripts/check_env.py` avisa |
| Autorização por área | Implementado | Rotas separadas (público / corretor / admin / operação) |
| Estado OAuth assinado (HMAC) | Implementado | `seguranca/oauth.py` protege o retorno do Google Agenda |
| Sessão assinada do chat do site | Implementado | `SDR_SESSAO_SECRET` impede sequestro de sessão |
| Chave por finalidade | Implementado | `seguranca/chaves.py`: sessão, `state` do OAuth e cofre usam chaves distintas derivadas (HMAC-SHA256) de `SDR_SESSAO_SECRET` — uma assinatura de uma nunca vale na outra |
| Segredo de exemplo recusado | Implementado | Com o `SDR_SESSAO_SECRET` que já esteve nos `.env.example`, os serviços não sobem (`seguranca/subida.py`) e `check_env.py` acusa erro. Vazio: chave aleatória por processo, com aviso |
| Cifra do refresh token do Google | Implementado | `seguranca/cofre.py`, Fernet: grava `enc:v2:` (chave derivada); lê `enc:v1:` e regrava como v2 na primeira leitura, sem reconectar a agenda |
| Sanitização de entrada | Implementado | `MensagemNormalizada`: trunca tamanho, remove controles / invisíveis; `meta` com teto de 16 campos / 2 KB |
| `meta` do navegador | Implementado | No canal web, `nome`/`telefone` do `meta` não criam contato; `imovel_origem` só no formato de id; os ids entram no prompt como dado envelopado |
| Contato autodeclarado × CRM | Implementado | Telefone/e-mail digitado no chat não vincula à ficha de um cliente existente nem herda as preferências dele; a coincidência é sinalizada ao corretor (`cliente.contato_coincide`) e a ficha aberta no CRM é nova |
| Guardrail de escopo (prompt injection) | Implementado | `guardrails/escopo.py`: recusa reprogramação, homóglifos e off-topic sem chamar o LLM |
| Blindagem de prompt | Implementado | Persona + cabeçalho de regras; texto do cliente em bloco com sentinela aleatória |
| Saneamento de saída | Implementado | `guardrails/saida.py`: descarta vazamento de instrução, mascara PII (CPF / cartão), remove tags / código / links |
| Injeção indireta via RAG | Implementado | Descrição de imóvel neutralizada antes de entrar no prompt |
| Rate limiting | Implementado | Por lead (rajada e hora) — `guardrails/vazao.py` |
| Auditoria | Implementado | Middleware registra tudo que altera o sistema; recusa 401/403/404 a quem não se autenticou e o `/eventos` público ficam fora (não dá para poluir a trilha); exportação CSV neutraliza fórmula (`=`, `+`, `-`, `@`) |
| Teto de corpo | Implementado | 256 KB na API e no CRM, pelo `Content-Length` e contando os bytes recebidos (`Transfer-Encoding: chunked`) — `limite_corpo.py` nos dois serviços |
| Upload de foto | Implementado | Assinatura JPEG/PNG/WebP conferida nos bytes; `/fotos` e `/acervo` com `X-Content-Type-Options: nosniff` |
| Login do CRM sem oráculo de tempo | Implementado | E-mail inexistente também passa pelo Argon2 (hash fictício) |
| CORS | Implementado | `SDR_CORS_ORIGINS`; vazio = só os front-ends locais no perfil local, nenhuma origem fora dele |
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

- O `dev-token` do painel continua valendo no perfil local sem `SDR_PAINEL_TOKEN` — é público. Só
  aceitável com as portas presas a `127.0.0.1`; o aviso no log ao subir existe para isso não passar
  despercebido.
- Trocar `SDR_SESSAO_SECRET` derruba as sessões de chat abertas e torna ilegíveis os refresh tokens
  da agenda cifrados com o segredo anterior (o corretor reconecta). A exceção são os cifrados com o
  valor de exemplo do repositório, que continuam legíveis e são regravados com a chave nova.
- O reconhecimento de cliente do CRM por contato está, na prática, desligado: nenhum canal entrega
  contato verificado. Cliente que volta pelo site recomeça do zero até o corretor juntar as fichas.

- Rate limiting é **por processo** (não distribuído entre múltiplos workers).
- Transcrição de áudio: já é tratada como **entrada não confiável** (entra blindada, como o texto do
  cliente), mas **não há teste adversarial específico** de injeção via áudio transcrito.
- Não há TLS: a entrega é local e nada é servido fora da máquina. Publicar isto em rede exigiria um
  proxy com certificado na frente, que não existe no repositório.

Os comentários em `services/agent/src/agent/guardrails/` detalham cada ponto.

## Dados pessoais e LGPD

Há mascaramento de PII na saída e uma página de privacidade no site. Uma **política formal de retenção
e exclusão** de dados é recomendada e ainda não existe (ver [Pendências](../project/pendencias.md)).
