---
title: Perguntas frequentes
description: Dúvidas comuns sobre o Mora — provedor de LLM, custo, canais, dados e produção.
---

# Perguntas frequentes

??? question "Preciso de conta em algum provedor de nuvem para rodar o Mora?"
    Não. Tudo sobe com `docker compose` na sua máquina, e você pode usar **Ollama** para um LLM 100%
    local, sem custo. Anthropic e OpenAI são alternativas que exigem uma chave de API.

??? question "Como rodar sem gastar tokens de LLM?"
    Suba com `--profile ollama` (`make local-ollama`) e baixe o modelo de embeddings `bge-m3`
    (`make ollama-pull`). Os testes de backend usam um LLM falso e não gastam token; `make eval-fake`
    também não.

??? question "Como conecto o Telegram?"
    No Telegram, fale com o **@BotFather** → `/newbot` → escolha um nome e um usuário (que precisa
    terminar em "bot"). Ele devolve um token na hora, sem aprovação e sem verificação de negócio.
    Cole o token em `SDR_TELEGRAM_BOT_TOKEN` e o usuário em `SDR_TELEGRAM_BOT_USERNAME`, no
    `local/.env`, e reinicie o compose. O worker `telegram-in` usa long polling (`getUpdates`): não
    há webhook, nem URL pública, nem túnel.

??? question "E o WhatsApp?"
    Não existe mais. O canal pela Cloud API da Meta foi removido do repositório: o webhook exige URL
    pública e conta de negócio verificada, o que não cabe numa entrega que roda na máquina de quem
    avalia (ADR-0007). O canal externo é o Telegram; há também o chat do site e a CLI.

??? question "O que acontece se o provedor de LLM cair?"
    Há um provedor de fallback (`SDR_LLM_PROVIDER_FALLBACK`) e um timeout por turno
    (`SDR_LLM_TIMEOUT_S`, padrão 45s). Ao estourar, o cliente recebe uma resposta de fallback e o lead
    é encaminhado ao corretor.

??? question "O catálogo aparece vazio. E agora?"
    Rode `make seed` para popular 200 imóveis e gerar os embeddings.

??? question "O Mora está pronto para produção?"
    Não. É uma **POC**, que roda na máquina de quem avalia e não está implantada em lugar nenhum.
    Veja [Roadmap e limitações](../project/roadmap.md) e [Segurança](../quality/seguranca.md).

??? question "Como entro no painel?"
    A tela de login pede o **token do painel** — o `SDR_PAINEL_TOKEN` do `local/.env`. Com ele em
    branco no perfil local, vale `dev-token`; fora do perfil local, em branco não entra ninguém. Não
    há cadastro nem provedor de identidade: o login por Cognito saiu junto com a AWS.

??? question "Onde vejo o custo de IA?"
    Na aba de **Governança** do painel: tokens, custo por modelo e a série diária. O consumo é
    registrado por chamada.

??? question "Como continuo uma conversa do site no Telegram?"
    O site tem um CTA de continuidade que abre o bot mantendo o contexto da conversa (ADR-0006).
