---
title: Swagger (OpenAPI)
description: Especificação OpenAPI completa da API do Mora, navegável e testável direto nesta página.
---

# Swagger — especificação completa

Todas as rotas, parâmetros, formatos de resposta e códigos de erro, gerados a partir do código.
A especificação abaixo é o arquivo [`openapi.json`](../assets/openapi.json){ #link-openapi }, versionado no
repositório e regerado por `make openapi` — a CI reprova o build se ele ficar diferente do código.

!!! tip "Para experimentar as rotas ('Try it out')"
    O botão **Try it out** chama a API de verdade, no endereço escolhido em **Servers**. Suba o
    ambiente local (`make local`) e mantenha `http://localhost:8000` selecionado.

    Rotas de corretor e de admin exigem credencial: clique em **Authorize**, escolha
    *Token do painel* e informe o valor de `SDR_PAINEL_TOKEN` — no ambiente de desenvolvimento,
    `dev-token`. As rotas com cadeado só respondem depois disso.

!!! note "Com o backend no ar, há duas alternativas a esta página"
    `http://localhost:8000/docs` (o mesmo Swagger, servido pela própria API) e
    `http://localhost:8000/redoc` (a mesma especificação em leitura contínua, melhor para imprimir).

<div id="swagger-ui" markdown="0"></div>

<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui.css">
<script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui-bundle.js"></script>
<script>
  // `navigation.instant` do Material troca a página sem recarregar o documento: sem reagir a isso,
  // o Swagger só apareceria em quem chegasse aqui por link direto ou F5.
  function montarSwagger() {
    var alvo = document.getElementById("swagger-ui");
    if (!alvo || alvo.dataset.pronto === "1" || typeof SwaggerUIBundle === "undefined") return;
    alvo.dataset.pronto = "1";
    // O endereço vem do link acima em vez de estar escrito aqui: o MkDocs reescreve o href do
    // markdown para o caminho certo do site construído (../../assets/…), mas não toca em strings
    // dentro de <script> — um caminho fixo aqui quebraria em silêncio, sem falhar o build.
    var origem = document.getElementById("link-openapi");
    SwaggerUIBundle({
      url: origem ? origem.getAttribute("href") : "../../assets/openapi.json",
      dom_id: "#swagger-ui",
      deepLinking: true,
      docExpansion: "none",
      defaultModelsExpandDepth: 0,
      persistAuthorization: true,
      tryItOutEnabled: true,
      presets: [SwaggerUIBundle.presets.apis],
    });
  }
  document.addEventListener("DOMContentLoaded", montarSwagger);
  if (typeof document$ !== "undefined") { document$.subscribe(montarSwagger); }  // Material
  montarSwagger();
</script>
