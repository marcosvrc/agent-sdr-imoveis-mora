/** Metadados por rota, sem biblioteca.
 *
 *  O site é uma SPA: sem isto, as 200 fichas compartilham o mesmo <title> e a mesma description do
 *  index.html — para o buscador e para quem cola o link no WhatsApp, são todas a mesma página.
 *
 *  Cobre o que muda por rota: title, description, canonical, Open Graph, Twitter e JSON-LD.
 *  Escrever direto no `document` (em vez de react-helmet) evita uma dependência para ~60 linhas e
 *  funciona igual: o navegador e o rastreador que executa JS leem o DOM, não o React.
 *
 *  Limite conhecido e assumido: rastreador que NÃO executa JS continua vendo só o shell. Quem cobre
 *  esse caso é `scripts/gerar-paginas.mjs`, que grava as mesmas tags no HTML de cada rota no build.
 */
import { useEffect } from "react";

export const SITE = import.meta.env.VITE_SITE_URL ?? "https://www.verticeimoveis.exemplo.br";

export type Seo = {
  titulo: string;
  descricao: string;
  caminho?: string;                 // canonical relativo, ex.: /imovel/xxx
  imagem?: string;
  tipo?: "website" | "article";
  naoIndexar?: boolean;             // favoritos, por exemplo: página pessoal, não tem o que indexar
  jsonLd?: Record<string, unknown> | Record<string, unknown>[];
};

const seletor = (nome: string, prop = false) =>
  `meta[${prop ? "property" : "name"}="${nome}"]`;

function meta(nome: string, valor: string, prop = false) {
  let el = document.head.querySelector<HTMLMetaElement>(seletor(nome, prop));
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute(prop ? "property" : "name", nome);
    document.head.appendChild(el);
  }
  el.content = valor;
}

function link(rel: string, href: string) {
  let el = document.head.querySelector<HTMLLinkElement>(`link[rel="${rel}"]`);
  if (!el) {
    el = document.createElement("link");
    el.rel = rel;
    document.head.appendChild(el);
  }
  el.href = href;
}

const ID_JSONLD = "jsonld-rota";

export function aplicarSeo(s: Seo): void {
  const url = SITE + (s.caminho ?? window.location.pathname);
  document.title = s.titulo;
  meta("description", s.descricao);
  meta("robots", s.naoIndexar ? "noindex, follow" : "index, follow");
  link("canonical", url);

  meta("og:title", s.titulo, true);
  meta("og:description", s.descricao, true);
  meta("og:url", url, true);
  meta("og:type", s.tipo ?? "website", true);
  meta("og:site_name", "Vértice Imóveis", true);
  meta("og:locale", "pt_BR", true);
  if (s.imagem) meta("og:image", s.imagem, true);

  meta("twitter:card", s.imagem ? "summary_large_image" : "summary");
  meta("twitter:title", s.titulo);
  meta("twitter:description", s.descricao);
  if (s.imagem) meta("twitter:image", s.imagem);

  document.getElementById(ID_JSONLD)?.remove();
  if (s.jsonLd) {
    const tag = document.createElement("script");
    tag.type = "application/ld+json";
    tag.id = ID_JSONLD;
    tag.textContent = JSON.stringify(s.jsonLd);
    document.head.appendChild(tag);
  }
}

export function useSeo(s: Seo, deps: unknown[] = []): void {
  useEffect(() => { aplicarSeo(s); }, deps);   // eslint-disable-line react-hooks/exhaustive-deps
}

/** Trilha de migalhas em dado estruturado — é o que faz o Google mostrar
 *  "Início › Imóveis › Brooklin" no lugar da URL crua no resultado da busca. */
export const trilhaJsonLd = (itens: { nome: string; caminho: string }[]) => ({
  "@context": "https://schema.org",
  "@type": "BreadcrumbList",
  itemListElement: itens.map((it, i) => ({
    "@type": "ListItem", position: i + 1, name: it.nome, item: SITE + it.caminho,
  })),
});
