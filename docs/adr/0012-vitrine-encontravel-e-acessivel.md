# ADR-0012 — Vitrine encontrável, pesquisável e acessível

**Status:** aceito · **Data:** 2026-09-12

## Contexto

O [ADR-0006](0006-site-vitrine-com-agente-embutido.md) decidiu manter `apps/web` como canal de
captação. Uma auditoria de UX, acessibilidade, SEO e conversão sobre o site como estava encontrou
quatro problemas estruturais — não de estilo:

1. **Invisível para busca.** SPA servida por S3 + CloudFront, com um único `<title>` e uma única
   description para todas as rotas. As 200 fichas eram a mesma página para o buscador e para quem
   colava o link no WhatsApp. Sem sitemap, sem robots.txt, sem dado estruturado, sem favicon, e o
   manifest do PWA declarava `icons: []` (inválido).
2. **Busca rasa.** A base tem 18 bairros, três tipos, suítes, vagas e área; o filtro oferecia
   operação, região, quartos e preço máximo — e a API pública aceitava só esses quatro. Quem
   quisesse "dois quartos com suíte em Perdizes" tinha que rolar a Zona Oeste inteira.
3. **Conversão escondida no celular.** Na ficha, o botão "conversar sobre este imóvel" vivia num
   `<aside>` que empilha depois da descrição: a duas telas de rolagem do preço.
4. **Sem identidade nem base legal.** Nenhum CRECI, endereço ou telefone — obrigatórios para
   anúncio imobiliário no Brasil e o primeiro sinal de confiança que um visitante procura. E nenhum
   aviso de privacidade, embora o chat colete nome, telefone e e-mail e o site registre navegação.

Havia ainda dívida acumulada: botão principal reescrito à mão em doze lugares, interativos
aninhados (o botão de favorito dentro do `<a>` do card; as setas da galeria como `<span onClick>`
dentro de um `<button>`), texto em `slate-400` (2,8:1), alvos de toque de 24px, nenhum respeito a
`prefers-reduced-motion`, e a home baixando os 200 imóveis do catálogo para exibir seis.

## Decisão

Reescrever a camada de apresentação de `apps/web` sobre um conjunto mínimo de tokens e primitivos,
preservando a arquitetura do ADR-0006 (o site continua sendo um canal burro sob o ADR-0003) e a
identidade visual existente (navy + Fraunces/Inter). Cinco frentes:

**1. Tokens e primitivos.** `src/index.css` define cor, raio e sombra como custom properties;
`tailwind.config.js` só mapeia. `src/lib/ui.tsx` traz `Botao`, `BotaoLink`, `BotaoIcone`, `Cartao`,
`Selo`, `Chip`, `Campo`, `Entrada`, `Escolha`, `Esqueleto`, `EstadoVazio`, `EstadoErro`, `Secao`.
Regra: primitivo não sabe o que é um imóvel. Ícones em `components/Icones.tsx`, inline — são
traços, não valem uma dependência.

**2. Encontrabilidade.** `lib/seo.ts` aplica título, descrição, canônica, Open Graph, Twitter e
JSON-LD por rota, escrevendo direto no `document`. URLs passam a ter slug
(`/imovel/apartamento-2-quartos-brooklin-sp-0001`, com o id no fim, então o slug pode mudar sem
quebrar link antigo) e `/imoveis/:operacao/:bairro` vira página fixa por bairro. O pós-build
`scripts/gerar-paginas.mjs` grava um HTML por rota com essas tags já no servidor — meta-prerender,
não SSR — mais `sitemap.xml` (238 rotas) e `robots.txt`.

**3. Busca.** Nova rota `GET /imoveis/busca` (`ImovelRepository.buscar_publico`) com bairro, tipo,
suítes, vagas, área e faixa de preço, ordenação, paginação por `offset`, `total` e contagem por
bairro. `GET /imoveis` fica intacto, porque o chat e os testes existentes dependem dele. A busca
textual usa `unaccent` — "perdizes" acha "Perdizes". A contagem por bairro ignora o próprio filtro
de bairro: uma lista que some quando você escolhe um item não serve para trocar de escolha.

**4. Confiança e conversão.** Bloco de identificação legal (CRECI, CNPJ, endereço, horário,
responsável técnico), aviso de privacidade dedicado, barra de CTA fixa no celular, custo mensal com
IPTU estimado, simulação de parcela pela Tabela Price, compartilhar, e "vistos recentemente" —
devolvendo ao visitante o histórico que já era coletado para o agente.

**5. Acessibilidade e desempenho.** Alvo em WCAG 2.2 AA, verificado por axe-core
(`scripts/verificar-acessibilidade.mjs`) em sete rotas × dois tamanhos. Rotas e chat carregam sob
demanda; `vendor` sai em chunk próprio.

**Placeholders, não invenções.** `lib/imobiliaria.ts` marca cada dado institucional que ainda não é
real, e a interface o exibe com um selo "exemplo" visível. Nada de CRECI, avaliação, depoimento,
prêmio ou número de vendas inventado — inclusive no JSON-LD, onde credencial falsa vira declaração
legível por máquina.

## Consequências

**A favor**

- Cada ficha e cada bairro têm título, descrição, canônica e `RealEstateListing` próprios, servidos
  no HTML. É a diferença entre não existir para a busca e concorrer por "apartamento em Perdizes".
- A busca finalmente alcança o dado que já existia: onze filtros contra quatro.
- Zero violação grave de acessibilidade em 14 combinações rota × viewport. Interativos aninhados,
  foco em diálogo, contraste, alvo de toque e movimento reduzido resolvidos.
- A home pede 6 imóveis em vez de 200; a ficha pede os parecidos filtrados pelo servidor.
- Um `Botao` em vez de doze botões: mudar o estilo do CTA agora é uma linha.
- O visitante tem, pela primeira vez, como saber quem é a imobiliária e o que acontece com seus dados.

**Contra, e assumido**

- **Não é SSR.** O corpo continua sendo o shell hidratado; só o `<head>` é pré-gerado. Rastreador
  que não executa JS vê metadados corretos e conteúdo vazio. Se indexação de conteúdo virar
  requisito, o caminho é SSG/SSR de verdade, não mais remendo no script.
- **O prerender depende de infraestrutura.** `FrontendStack` ganhou uma CloudFront Function que
  reescreve `/rota` para `/rota/index.html`; sem ela, o S3 devolve 404, a regra de SPA entrega o
  shell genérico e o pré-render não serve para nada. É um acoplamento novo entre build e infra.
- **O build agora depende da API.** `gerar-paginas.mjs` lê o catálogo para montar sitemap e fichas.
  Sem API no ar ele degrada para as rotas fixas e avisa — não quebra o build, mas publica menos.
- **Sitemap estático.** Imóvel cadastrado depois do build só entra no próximo deploy.
- **Duas rotas de leitura no catálogo.** `GET /imoveis` e `GET /imoveis/busca` coexistem. É o preço
  de não quebrar consumidor existente; a antiga deve sair quando nada mais depender dela.
- **O teste de acessibilidade é automático.** Cobre cerca de um terço dos problemas reais. Ordem de
  tabulação, clareza de rótulo e destino do foco continuam exigindo verificação humana.

## Alternativas consideradas

**Next.js (SSR/SSG).** Resolveria indexação de conteúdo de uma vez. Custa trocar hospedagem
estática (S3 + CloudFront, ADR-0006) por runtime — Lambda@Edge, Amplify ou container —, muda o
modelo de custo e contradiz "em produção é hospedagem estática, não mais um serviço rodando". Para
um catálogo de 200 imóveis, o meta-prerender entrega a maior parte do ganho sem essa troca.

**react-helmet-async para metadados.** Faz o mesmo que `lib/seo.ts` em ~60 linhas nossas, com uma
dependência a mais e sem resolver o caso do rastreador sem JS — que é justamente o problema.

**Biblioteca de componentes pronta (shadcn/ui, MUI).** Consistência imediata, mas o site tem doze
componentes e uma identidade própria já definida; adotar um sistema inteiro para isso é mais código
para manter, não menos.

**Manter `GET /imoveis` e só acrescentar parâmetros.** Mais simples, porém a paginação exige devolver
`total` — o que mudaria a forma da resposta e quebraria o contrato de quem já consome a lista.
