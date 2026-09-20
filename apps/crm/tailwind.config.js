/** @type {import('tailwindcss').Config} */
// Os nomes continuam os mesmos que as telas já usavam; os VALORES viraram variáveis (ver
// src/index.css). Foi isso que permitiu acrescentar o tema escuro sem tocar numa classe sequer das
// páginas — a classe continua `bg-surface`, muda o que `--surface` vale.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "var(--canvas)", surface: "var(--surface)", surface2: "var(--surface2)",
        line: "var(--line)", lineForte: "var(--line-forte)",
        ink: "var(--ink)", inkSoft: "var(--ink-soft)", inkMuted: "var(--ink-muted)", inkFaint: "var(--ink-faint)",
        marca: "var(--marca)", marcaInk: "var(--marca-ink)", acento: "var(--acento)",
        bom: "var(--bom)", bomSoft: "var(--bom-soft)", alerta: "var(--alerta)", alertaSoft: "var(--alerta-soft)",
        ruim: "var(--ruim)", ruimSoft: "var(--ruim-soft)", info: "var(--info)", infoSoft: "var(--info-soft)",
      },
      boxShadow: { card: "var(--sombra-card)" },
    },
  },
};
