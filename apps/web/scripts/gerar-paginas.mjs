/**
 * Pós-build: gera sitemap.xml e um HTML por rota indexável.
 *
 * O problema que resolve: o site é uma SPA servida por S3 + CloudFront. Todo endereço devolve o
 * mesmo index.html, com o mesmo <title> e a mesma description — para o rastreador que não executa
 * JavaScript, e para o WhatsApp/LinkedIn quando alguém cola o link, as 200 fichas são a mesma
 * página. Este script grava, em cada rota, um HTML com as tags certas já no servidor.
 *
 * O que ele NÃO faz: renderizar o conteúdo. O corpo continua sendo o shell hidratado pelo React —
 * é meta-prerender, não SSR. Cobre título, descrição, canônica, Open Graph e dado estruturado, que
 * é o que decide indexação e resultado rico. Renderizar o HTML do catálogo exigiria um navegador no
 * build ou um servidor; se isso virar requisito, o caminho é trocar Vite por SSR/SSG de verdade.
 *
 * Uso:  node scripts/gerar-paginas.mjs
 * Lê a API em VITE_API_URL. Sem API no ar, gera só as rotas estáticas e avisa — o build não quebra
 * por causa disso: publicar sem sitemap é ruim, publicar nada é pior.
 */
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";

const DIST = "dist";
const API = process.env.VITE_API_URL ?? "http://localhost:8000";
const SITE = (process.env.VITE_SITE_URL ?? "https://www.verticeimoveis.exemplo.br").replace(/\/$/, "");
const HOJE = new Date().toISOString().slice(0, 10);

const paraSlug = (s) => s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase()
  .replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
const escapar = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const brl = (v) => v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
const TIPOS = { apartamento: "Apartamento", casa: "Casa", studio: "Studio" };
// Mesma regra de src/lib/api.ts: "em <bairro>", que é sempre correto — o artigo do bairro varia.
const nomeImovel = (im) =>
  `${TIPOS[im.tipo] ?? im.tipo}${im.quartos > 0 ? ` de ${im.quartos} quarto${im.quartos === 1 ? "" : "s"}` : ""} em ${im.bairro}`;

async function catalogo() {
  try {
    const r = await fetch(`${API}/imoveis?limite=200`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return await r.json();
  } catch (e) {
    console.warn(`[gerar-paginas] catálogo indisponível em ${API} (${e.message}). Gerando só as rotas fixas.`);
    return [];
  }
}

/** Reescreve as tags do shell. Substitui em vez de acrescentar: duas <title> ou duas canônicas
 *  numa página é pior do que uma errada, porque o buscador escolhe sozinho qual respeitar. */
function pagina(shell, { titulo, descricao, caminho, imagem, tipo = "website", noindex, jsonLd }) {
  const url = SITE + caminho;
  let html = shell
    .replace(/<title>[\s\S]*?<\/title>/, `<title>${escapar(titulo)}</title>`)
    .replace(/<meta name="description"[^>]*>/, `<meta name="description" content="${escapar(descricao)}" />`)
    .replace(/<link rel="canonical"[^>]*>/, `<link rel="canonical" href="${escapar(url)}" />`)
    .replace(/<meta property="og:title"[^>]*>/, `<meta property="og:title" content="${escapar(titulo)}" />`)
    .replace(/<meta property="og:description"[^>]*>/, `<meta property="og:description" content="${escapar(descricao)}" />`)
    .replace(/<meta property="og:url"[^>]*>/, `<meta property="og:url" content="${escapar(url)}" />`)
    .replace(/<meta property="og:type"[^>]*>/, `<meta property="og:type" content="${tipo}" />`);

  const extras = [];
  if (imagem) {
    extras.push(`<meta property="og:image" content="${escapar(imagem)}" />`);
    extras.push(`<meta name="twitter:image" content="${escapar(imagem)}" />`);
    html = html.replace(/<meta name="twitter:card"[^>]*>/, `<meta name="twitter:card" content="summary_large_image" />`);
  }
  if (noindex) extras.push(`<meta name="robots" content="noindex, follow" />`);
  if (jsonLd) extras.push(`<script type="application/ld+json">${JSON.stringify(jsonLd).replace(/</g, "\\u003c")}</script>`);
  return html.replace("</head>", `${extras.join("\n    ")}\n  </head>`);
}

async function gravar(caminho, html) {
  const destino = caminho === "/" ? join(DIST, "index.html") : join(DIST, caminho.replace(/^\//, ""), "index.html");
  await mkdir(dirname(destino), { recursive: true });
  await writeFile(destino, html, "utf8");
}

const main = async () => {
  const shell = await readFile(join(DIST, "index.html"), "utf8");
  const imoveis = await catalogo();
  const rotas = [];

  rotas.push({ caminho: "/", prioridade: "1.0", freq: "daily" });
  await gravar("/", pagina(shell, {
    titulo: "Vértice Imóveis — apartamentos e casas em São Paulo",
    descricao: "Compra e aluguel de imóveis em São Paulo com atendimento imediato: converse com a Mora, receba sugestões do catálogo e agende a visita sem espera.",
    caminho: "/",
    jsonLd: {
      "@context": "https://schema.org", "@type": "RealEstateAgent",
      name: "Vértice Imóveis", url: SITE,
      areaServed: { "@type": "City", name: "São Paulo" },
    },
  }));

  rotas.push({ caminho: "/imoveis", prioridade: "0.9", freq: "daily" });
  await gravar("/imoveis", pagina(shell, {
    titulo: `Imóveis à venda e para alugar em São Paulo${imoveis.length ? ` — ${imoveis.length} opções` : ""} | Vértice Imóveis`,
    descricao: "Todo o catálogo da Vértice Imóveis: filtre por bairro, tipo, preço, quartos, suítes e vagas — e agende a visita conversando com a Mora.",
    caminho: "/imoveis",
  }));

  await gravar("/privacidade", pagina(shell, {
    titulo: "Privacidade e uso de dados | Vértice Imóveis",
    descricao: "Quais dados coletamos neste site, para que usamos, por quanto tempo guardamos e como você exerce seus direitos previstos na LGPD.",
    caminho: "/privacidade",
  }));
  rotas.push({ caminho: "/privacidade", prioridade: "0.3", freq: "yearly" });

  await gravar("/favoritos", pagina(shell, {
    titulo: "Meus favoritos | Vértice Imóveis",
    descricao: "Os imóveis que você salvou neste navegador.",
    caminho: "/favoritos", noindex: true,
  }));

  // Uma página por bairro e operação — é como as pessoas procuram ("apartamento em Perdizes"),
  // e é a malha que dá ao buscador um caminho para as fichas.
  const porBairro = new Map();
  for (const im of imoveis) {
    const chave = `${im.operacao}|${im.bairro}`;
    porBairro.set(chave, (porBairro.get(chave) ?? 0) + 1);
  }
  for (const [chave, n] of porBairro) {
    const [operacao, bairro] = chave.split("|");
    const caminho = `/imoveis/${operacao}/${paraSlug(bairro)}`;
    rotas.push({ caminho, prioridade: "0.8", freq: "weekly" });
    await gravar(caminho, pagina(shell, {
      titulo: `Imóveis ${operacao === "aluguel" ? "para alugar" : "à venda"} em ${bairro}, São Paulo | Vértice Imóveis`,
      descricao: `${n} ${n === 1 ? "imóvel" : "imóveis"} ${operacao === "aluguel" ? "para alugar" : "à venda"} em ${bairro}. Veja fotos, preço, área e condomínio — e agende a visita falando com a Mora.`,
      caminho,
    }));
  }

  for (const im of imoveis) {
    const caminho = `/imovel/${paraSlug(`${im.tipo}${im.quartos > 0 ? `-${im.quartos}-quartos` : ""}-${im.bairro}-${im.id}`)}`;
    rotas.push({ caminho, prioridade: "0.7", freq: "weekly" });
    await gravar(caminho, pagina(shell, {
      titulo: `${nomeImovel(im)} — ${brl(im.preco)}${im.operacao === "aluguel" ? "/mês" : ""} | Vértice Imóveis`,
      descricao: `${nomeImovel(im)}, ${im.area_m2} m²${im.vagas ? `, ${im.vagas} vaga(s)` : ""}, em ${im.bairro}, ${im.cidade}. ${im.descricao}`.slice(0, 300),
      caminho, tipo: "article", imagem: im.fotos?.[0],
      jsonLd: {
        "@context": "https://schema.org", "@type": "RealEstateListing",
        name: nomeImovel(im), description: im.descricao, url: SITE + caminho,
        ...(im.fotos?.length ? { image: im.fotos } : {}),
        offers: { "@type": "Offer", price: im.preco, priceCurrency: "BRL", availability: "https://schema.org/InStock" },
        about: {
          "@type": im.tipo === "casa" ? "House" : "Apartment",
          numberOfRoomsTotal: im.quartos,
          floorSize: { "@type": "QuantitativeValue", value: im.area_m2, unitCode: "MTK" },
          address: { "@type": "PostalAddress", streetAddress: im.bairro, addressLocality: im.cidade, addressRegion: "SP", addressCountry: "BR" },
        },
      },
    }));
  }

  const sitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${rotas.map((r) => `  <url><loc>${SITE}${r.caminho}</loc><lastmod>${HOJE}</lastmod><changefreq>${r.freq}</changefreq><priority>${r.prioridade}</priority></url>`).join("\n")}
</urlset>
`;
  await writeFile(join(DIST, "sitemap.xml"), sitemap, "utf8");
  console.log(`[gerar-paginas] ${rotas.length} rotas no sitemap · ${imoveis.length} fichas · ${porBairro.size} páginas de bairro`);
};

main().catch((e) => { console.error("[gerar-paginas] falhou:", e); process.exit(1); });
