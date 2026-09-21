// Confere cada SVG de diagrama no navegador: nenhum texto pode transbordar da caixa que o contém
// nem sair do quadro. Um diagrama desenhado por coordenadas erra silenciosamente — este é o teste
// que impede o erro de chegar ao portal.
//
//   npm i --no-save playwright   (uma vez)
//   node scripts/diagramas/verificar.mjs docs/assets/diagramas/*.svg
//
// Sai com código 1 quando encontra problema, para poder entrar na CI.
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';

const arquivos = process.argv.slice(2);
const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
const p = await (await b.newContext({ deviceScaleFactor: 1 })).newPage();
let problemas = 0;

for (const f of arquivos) {
  const svg = fs.readFileSync(f, 'utf8');
  const m = svg.match(/viewBox="0 0 (\d+) (\d+)"/);
  const [W, H] = [Number(m[1]), Number(m[2])];
  await p.setViewportSize({ width: W, height: H });
  await p.setContent(`<body style="margin:0">${svg}</body>`);
  await p.waitForTimeout(120);

  // conferência: todo <text> precisa caber dentro de algum <rect> que o contenha,
  // e não pode encostar na borda do desenho
  const achados = await p.evaluate((W) => {
    const out = [];
    const rects = [...document.querySelectorAll('rect')].map(r => {
      const b = r.getBBox();
      return { x: b.x, y: b.y, w: b.width, h: b.height, cls: r.getAttribute('class') || '' };
    }).filter(r => /cartao|grupo/.test(r.cls));
    for (const t of document.querySelectorAll('text')) {
      const b = t.getBBox();
      const txt = (t.textContent || '').slice(0, 42);
      if (b.x < 2 || b.x + b.width > W - 2) { out.push(`fora do quadro: "${txt}"`); continue; }
      // o cartão mais justo que contém o ponto inicial do texto
      const dentro = rects.filter(r => b.x + 1 >= r.x && b.x + 1 <= r.x + r.w &&
                                       b.y + b.height / 2 >= r.y && b.y + b.height / 2 <= r.y + r.h)
                          .sort((a, c) => (a.w * a.h) - (c.w * c.h))[0];
      if (dentro && /cartao/.test(dentro.cls) && b.x + b.width > dentro.x + dentro.w - 4)
        out.push(`transborda do cartão: "${txt}" (+${Math.round(b.x + b.width - dentro.x - dentro.w)}px)`);
    }
    return out;
  }, W);

  if (achados.length) { problemas += achados.length; console.log(`\n### ${path.basename(f)}`); achados.forEach(a => console.log('  ' + a)); }
  const png = process.env.DIAGRAMAS_PNG && path.join(process.env.DIAGRAMAS_PNG, path.basename(f).replace(/\.svg$/, '.png'));
  if (png) {
    fs.mkdirSync(path.dirname(png), { recursive: true });
    await p.screenshot({ path: png, clip: { x: 0, y: 0, width: W, height: H } });
  }
}
console.log(problemas ? `\n${problemas} problema(s)` : `\n${arquivos.length} diagrama(s) conferido(s): sem transbordo`);
await b.close();
if (problemas) process.exit(1);
