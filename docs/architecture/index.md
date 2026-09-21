---
title: Arquitetura — visão geral
description: Como o Mora separa o cérebro (agente) dos canais, e como o sistema inteiro roda em docker compose.
---

# Arquitetura — visão geral

O sistema separa o **cérebro** (o agente) dos **canais** (Telegram, web, CLI). O agente não sabe por
qual canal a mensagem chegou: cada canal traduz `evento do provedor → MensagemNormalizada` e
`RespostaAgente → formato do canal`. A única dependência cruzada permitida é o pacote `shared/`.

Tudo roda como container em [`local/docker-compose.yml`](https://github.com/marcosvrc/agent-sdr-imoveis-mora/blob/master/local/docker-compose.yml):
Postgres com pgvector, Redis como broker, os workers do agente, os canais, a API, os front-ends
Vite e o CRM com o seu servidor MCP. **Nada está implantado** — é escolha de escopo, e o efeito é
que quem abre o repositório sobe o sistema inteiro sem conta em provedor nenhum.

Cada dependência externa entra por uma porta (`shared/sdr_shared/ports`), resolvida em
`shared/sdr_shared/adapters/`. Hoje broker, scheduler e embeddings têm uma implementação cada;
`get_calendario` e `get_crm` têm duas de verdade, e escolhem por configuração presente, não por
perfil. `SDR_PROFILE` (`local` | `producao`) decide apenas se o token estático de desenvolvimento
vale.

## Princípios de arquitetura

1. **Roda inteiro na máquina de quem avalia** — `docker compose up` sobe o sistema completo, sem
   conta em provedor, sem túnel e sem URL pública.
2. **Cérebro separado dos canais** — o agente não sabe se está no Telegram ou na web.
3. **Cada componente na sua pasta** — dependências e testes independentes; `shared/` é a única ponte.
4. **Reversibilidade** — cada dependência externa entra por uma porta; trocá-la é escrever um
   adaptador, não redesenhar o sistema.

## Diagrama de contexto

![Arquitetura macro do Mora](../assets/diagramas/macro-claro.svg#only-light)
![Arquitetura macro do Mora](../assets/diagramas/macro-escuro.svg#only-dark)

### Leitura do diagrama

- **Componentes.** Front-ends (`web`, `dashboard`), canais, fila, agente, LLM, banco, API e a ponte
  com o CRM.
- **Responsabilidades.** Os canais só traduzem mensagens; o agente é o único que fala com o LLM; a API
  serve dados ao painel.
- **Comunicação.** Cliente → canal → fila → agente → LLM/banco → resposta neutra → fila → canal. O
  painel fala com a API (REST) e com os canais (tempo real, somente leitura).
- **Decisões importantes.** A fila desacopla canal e agente, porque um turno leva de 20 a 40 s e não
  cabe no fio do HTTP; as portas isolam cada dependência externa.
- **Limites.** O agente não conhece o canal de origem; os canais não têm regra de negócio.
- **Pontos de falha.** Redis, provedor de LLM e Postgres. Health checks e o provedor de reserva
  (`SDR_LLM_PROVIDER_FALLBACK`) mitigam parte disso — veja
  [Troubleshooting](../quality/troubleshooting.md).

## Onde aprofundar

- [Componentes](componentes.md) — o papel de cada pasta.
- [Fluxo do agente e LLM](fluxo-agente.md) — máquina de estados do lead e blindagem de prompt.
- [Dados e persistência](dados.md) — Postgres, pgvector e RAG.
- [Decisões arquiteturais (ADRs)](decisoes.md) — os registros de decisão.
- [Diagramas](diagramas.md) — a topologia do compose e todos os fluxos.

!!! note "Referência completa"
    A [Referência completa (ARCHITECTURE.md)](../ARCHITECTURE.md) traz o desenho detalhado, os
    contratos entre camadas e o que o sistema custa para rodar. Há também um dossiê visual C4 em
    [`arquitetura.html`](../arquitetura.html){ target=_blank } (abra no navegador).
