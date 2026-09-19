---
title: Pendências de documentação
description: Informações que não puderam ser confirmadas apenas com o conteúdo do repositório.
---

# Pendências de documentação

Informações que não puderam ser confirmadas apenas com o conteúdo do repositório:

!!! note "O que não é pendência"
    Não implantar em nuvem é **escolha declarada**, não item em aberto: a entrega é o
    `local/docker-compose.yml` e roda inteira na máquina de quem avalia. Veja
    [Execução e custo](../ARCHITECTURE.md#10-execucao-e-custo).

1. **Canal de suporte** oficial (a autoria está definida: Marcos Ramos).
2. **Requisitos de hardware** mínimo / recomendado para rodar o compose (sobretudo com Ollama e o
   `faster-whisper` no mesmo processo).
3. **Papéis e permissões** granulares por usuário no painel (a API separa por área, mas o mapeamento
   usuário → papel não está documentado).
4. **Benchmarks de performance** (nenhum número medido versionado).
5. **Convenção de commits, template de PR e processo de revisão** formais.
6. **Política de retenção e exclusão de dados** (LGPD) formal.

!!! tip "Converter em issues"
    A sugestão é transformar cada item em uma issue do repositório e, quando resolvida, atualizar as
    seções correspondentes da documentação.
