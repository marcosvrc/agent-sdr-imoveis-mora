/** Tokens em src/index.css (custom properties); aqui só o mapeamento para as classes.
 *  Uma cor nova entra lá, não aqui — assim tema e componente nunca discordam. */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { DEFAULT: "var(--ink)", muted: "var(--ink-muted)", soft: "var(--ink-soft)" },
        brand: { DEFAULT: "var(--brand)", accent: "var(--accent)", accentDark: "var(--accent-forte)", suave: "var(--accent-suave)" },
        surface: { DEFAULT: "var(--surface)", 2: "var(--surface-2)" },
        ground: "var(--ground)",
        line: { DEFAULT: "var(--line)", forte: "var(--line-forte)" },
        estado: { ok: "var(--ok)", alerta: "var(--alerta)", erro: "var(--erro)" },
        sand: { 50: "var(--ground)", 100: "var(--surface-2)" },
      },
      borderRadius: { sm: "var(--raio-sm)", md: "var(--raio-md)", lg: "var(--raio-lg)", xl: "var(--raio-xl)", "2xl": "var(--raio-xl)" },
      boxShadow: { sm: "var(--sombra-sm)", card: "var(--sombra-md)", soft: "var(--sombra-lg)" },
      fontFamily: {
        display: ["\"Fraunces\"", "ui-serif", "Georgia", "serif"],
        sans: ["\"Inter\"", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      keyframes: {
        "fade-up": { "0%": { opacity: 0, transform: "translateY(8px)" }, "100%": { opacity: 1, transform: "translateY(0)" } },
        "pop-in": { "0%": { opacity: 0, transform: "scale(0.94) translateY(6px)" }, "100%": { opacity: 1, transform: "scale(1) translateY(0)" } },
      },
      animation: { "fade-up": "fade-up .5s ease-out both", "pop-in": "pop-in .18s ease-out both" },
    },
  },
  plugins: [],
};
