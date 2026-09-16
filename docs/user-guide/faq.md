---
title: Perguntas frequentes
description: Dúvidas comuns sobre o Mora — provedor de LLM, custo, canais, dados e produção.
---

# Perguntas frequentes

??? question "Preciso de conta AWS para rodar o Mora?"
    Não. O perfil local roda com Docker Compose e você pode usar **Ollama** para um LLM 100% local, sem
    custo. Bedrock e Anthropic API são alternativas que exigem credenciais.

??? question "Como rodar sem gastar tokens de LLM?"
    Use o perfil local com `--profile ollama` (`make local-ollama`) e o modelo de embeddings `bge-m3`
    (`make ollama-pull`). Os testes de backend usam um LLM falso e não gastam token.

??? question "O WhatsApp funciona?"
    O adapter está **implementado, mas desativado** no compose (ADR-0007), porque depende de um número
    de negócio verificado. O canal ativo é o Telegram.

??? question "O que acontece se o provedor de LLM cair?"
    Há um provedor de fallback (`SDR_LLM_PROVIDER_FALLBACK`) e um timeout por turno
    (`SDR_LLM_TIMEOUT_S`, padrão 45s). Ao estourar, o cliente recebe uma resposta de fallback e o lead
    é encaminhado ao corretor.

??? question "O catálogo aparece vazio. E agora?"
    Rode `make seed` para popular 200 imóveis e gerar os embeddings.

??? question "O Mora está pronto para produção?"
    Não. É uma **POC**. Vários controles dependentes de AWS não são exercitados localmente e não há
    benchmarks versionados. Veja [Roadmap e limitações](../project/roadmap.md) e
    [Segurança](../quality/seguranca.md).

??? question "Onde vejo o custo de IA?"
    Na aba de **Governança** do painel: tokens, custo por modelo e a série diária. O consumo é
    registrado por chamada.

??? question "Como continuo uma conversa do site no Telegram?"
    O site tem um CTA de continuidade que abre o bot mantendo o contexto da conversa (ADR-0006).
