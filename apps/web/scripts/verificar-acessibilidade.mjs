/**
 * Verificação automática de acessibilidade (axe-core / WCAG 2.2 AA) nas rotas principais.
 *
 * O que ele pega: contraste, rótulo faltando, ordem de cabeçalho, ARIA inválida, interativo
 * aninhado, imagem sem alt. O que ele NÃO pega — e por isso não substitui teste manual: se a ordem
 * de tabulação faz sentido, se o texto do rótulo é compreensível, se o foco vai para o lugar certo
 * ao abrir um diálogo. Regra prática do setor: automação cobre cerca de um terço dos problemas.
 *
 * `playwright` e `@axe-core/playwright` NÃO estão em devDependencies de propósito: o serviço `web`
 * do compose roda `npm install` num node:20-alpine a cada volume novo, e o pacote do Playwright
 * baixa ~130 MB de navegador no install — numa imagem onde ele nem roda. Ferramenta de verificação
 * não pode entrar no caminho de subir o ambiente. Instale quando for usar:
 *
 *     npm i --no-save playwright @axe-core/playwright && npx playwright install chromium
 *     npm run build && npx vite preview --port 4173 &
 *     BASE=http://localhost:4173 npm run a11y
 *
 * ROTAS e BASE são configuráveis; CHROME_PATH aponta um Chromium já instalado, se houver.
 */
const BASE = process.env.BASE ?? "http://localhost:4173";
const ROTAS = process.env.ROTAS?.split(",") ?? ["/", "/imoveis", "/favoritos", "/privacidade"];
const TAMANHOS = [{ nome: "celular", width: 390, height: 844 }, { nome: "desktop", width: 1440, height: 900 }];

const { chromium } = await import("playwright");
const { default: AxeBuilder } = await import("@axe-core/playwright");

const navegador = await chromium.launch(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {});
let falhas = 0;

for (const tam of TAMANHOS) {
  const ctx = await navegador.newContext({ viewport: { width: tam.width, height: tam.height } });
  const pagina = await ctx.newPage();
  for (const rota of ROTAS) {
    await pagina.goto(BASE + rota, { waitUntil: "networkidle" });
    const r = await new AxeBuilder({ page: pagina })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
      .analyze();
    const graves = r.violations.filter((v) => v.impact === "critical" || v.impact === "serious");
    falhas += graves.length;
    console.log(`${graves.length ? "✗" : "✓"} ${tam.nome} ${rota} — ${r.violations.length} achados (${graves.length} graves)`);
    for (const v of r.violations) {
      console.log(`    [${v.impact}] ${v.id}: ${v.help} (${v.nodes.length}x)`);
      for (const n of v.nodes.slice(0, 2)) console.log(`        ${n.target.join(" ")}`);
    }
  }
  await ctx.close();
}

await navegador.close();
console.log(falhas ? `\n${falhas} violação(ões) grave(s).` : "\nNenhuma violação grave.");
process.exit(falhas ? 1 : 0);
