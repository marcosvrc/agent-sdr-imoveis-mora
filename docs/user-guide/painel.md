---
title: Manual do painel administrativo
description: Acesso, autenticação, dashboards, gestão de dados, governança de IA e auditoria no painel do corretor.
---

# Manual do painel administrativo

## Acesso e autenticação

<http://localhost:5174>.

- **Perfil local** — autenticação por token estático (`SDR_PAINEL_TOKEN`, que vira `dev-token` quando
  vazio).
- **Perfil AWS** — Amazon Cognito.

!!! danger "Não use credenciais reais"
    Nunca utilize credenciais reais no repositório ou em exemplos. Em produção, gere o primeiro acesso
    pelo mecanismo do Cognito e mantenha os segredos no AWS Secrets Manager.

## Perfis e permissões

A API distingue rotas públicas, de corretor, de administração e de operação (ver [API](../technical-reference/api.md)).
O detalhamento de papéis por usuário é `A confirmar` — veja [Pendências](../project/pendencias.md).

## Principais áreas

| Área | O que faz |
|---|---|
| Visão geral | KPIs (key performance indicators) do período com variação. |
| Leads | Funil por estágio / temperatura / corretor; ficha do cliente. |
| Conversas ao vivo | Acompanhamento em tempo real das conversas. |
| Agenda | Visitas marcadas. |
| Imóveis | Cadastro, upload e reordenação de fotos. |
| Corretores | Gestão de corretores. |
| Configuração do agente | Follow-up, agenda, área de cobertura, handoff e modelos de IA por nível — sem redeploy (ADR-0010). |
| Governança de IA | Tokens, custo por modelo, limites e orçamento com degradação automática. |
| Auditoria | Registro de tudo que altera o sistema, com exportação. |
| Saúde do sistema | Observabilidade leve (ADR-0011). |

## Tema (claro, escuro ou o do sistema)

No canto superior direito, o ícone de sol/lua abre as três opções:

| Opção | O que faz |
| --- | --- |
| **Claro** | Sempre claro, independente do computador. |
| **Escuro** | Sempre escuro. |
| **Sistema** | Acompanha a preferência do macOS/Windows — e muda sozinha ao anoitecer, sem recarregar a página. |

É o padrão para quem nunca escolheu, e a escolha fica **naquele navegador**, não na conta: o mesmo
corretor pode usar claro no monitor do escritório e escuro no notebook. Os gráficos, os selos de
temperatura e os avisos acompanham o tema; o contraste foi verificado nos dois
([ADR-0014](../adr/0014-tema-claro-e-escuro-no-painel.md)).

## Operações sensíveis

!!! warning "Ações com efeito real"
    Assumir ou devolver um lead e responder pelo corretor **enviam mensagens reais** aos canais do
    lead. Alterar limites de orçamento afeta o comportamento do agente (degradar ou bloquear).

## Logout

Encerre a sessão pelo próprio painel. No perfil local, o token estático permanece válido enquanto
configurado; no perfil AWS, a sessão segue o ciclo do Cognito.
