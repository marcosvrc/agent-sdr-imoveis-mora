/** @type {import('tailwindcss').Config} */
// As cores apontam para variáveis CSS (definidas em src/index.css) em vez de hex literal: é o que
// permite trocar de tema em tempo de execução, sem recarregar e sem duplicar cada classe com `dark:`.
// Os nomes são de PAPEL, não de cor — ver o comentário no topo do index.css.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: "var(--brand)", accent: "var(--brand-accent)", ink: "var(--brand-ink)" },
        canvas: "var(--canvas)",
        surface: { DEFAULT: "var(--surface)", 2: "var(--surface-2)" },
        line: "var(--line)",
        ink: { DEFAULT: "var(--ink)", soft: "var(--ink-soft)", muted: "var(--ink-muted)", faint: "var(--ink-faint)" },
        status: { good: "var(--good)", warn: "var(--warn)", bad: "var(--bad)" },
        // Trio por tom: `-soft` é fundo, `-strong` é o texto sobre ele, `-line` é a borda.
        good: { DEFAULT: "var(--good)", soft: "var(--good-soft)", strong: "var(--good-strong)", line: "var(--good-line)" },
        warn: { DEFAULT: "var(--warn)", soft: "var(--warn-soft)", strong: "var(--warn-strong)", line: "var(--warn-line)" },
        bad: { DEFAULT: "var(--bad)", soft: "var(--bad-soft)", strong: "var(--bad-strong)", line: "var(--bad-line)" },
        info: { DEFAULT: "var(--info)", soft: "var(--info-soft)", strong: "var(--info-strong)", line: "var(--info-line)" },
        violeta: { DEFAULT: "var(--violeta)", soft: "var(--violeta-soft)", strong: "var(--violeta-strong)", line: "var(--violeta-line)" },
      },
      boxShadow: { card: "var(--sombra-card)" },
      fontFamily: { sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"] },
    },
  },
  plugins: [],
};
