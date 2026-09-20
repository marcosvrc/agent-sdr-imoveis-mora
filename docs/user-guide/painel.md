---
title: Manual do painel administrativo
description: Acesso, autenticação, dashboards, gestão de dados, governança de IA e auditoria no painel do corretor.
---

# Manual do painel administrativo

## Acesso e autenticação

<http://localhost:5174>.

A tela de login pede um **token do painel** — não há cadastro, nem provedor de identidade. O campo de
senha é o próprio `SDR_PAINEL_TOKEN`, e o painel o valida contra a API antes de guardá-lo (um token
errado é recusado ali, em vez de virar 401 na primeira tela). O campo de e-mail é só rótulo.

- **Perfil local** (`SDR_PROFILE=local`) — com `SDR_PAINEL_TOKEN` vazio, vale `dev-token`. É o que o
  campo em branco envia.
- **Fora do perfil local** — vazio não aceita nada: sem segredo configurado, ninguém entra.

O mesmo token vale para o header `Authorization` da API e para a conexão WebSocket `papel=dashboard`
— no WebSocket ele vai no primeiro quadro após abrir a conexão (`{"token": "..."}`), nunca na URL.
Havia aqui um login por Amazon Cognito, via `aws-amplify`; saiu junto com o resto da AWS.

!!! danger "Não use credenciais reais"
    Nunca utilize credenciais reais no repositório ou em exemplos. Gere o `SDR_PAINEL_TOKEN` como
    qualquer segredo forte (`python3 -c "import secrets; print(secrets.token_urlsafe(32))"`) e
    mantenha-o apenas no `local/.env`, que não vai para o repositório.

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

Encerre a sessão pelo próprio painel: o token guardado no navegador é apagado. Não há expiração — o
token continua válido enquanto estiver configurado, então revogar o acesso significa trocar o
`SDR_PAINEL_TOKEN` e reiniciar os serviços.
