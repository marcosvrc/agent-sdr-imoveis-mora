/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#f6f7f9", surface: "#ffffff", surface2: "#eef1f5", line: "#dfe3e9",
        ink: "#111827", inkSoft: "#374151", inkMuted: "#5b6472", inkFaint: "#606874",   // 5,6:1 no branco e 5,0:1 no realce — o tom anterior (#6b7480) reprovava em 11px
        marca: "#0f172a", acento: "#2563eb",
        bom: "#056608", bomSoft: "#e8f5e9", alerta: "#8a5a00", alertaSoft: "#fdf6e3",
        ruim: "#a52322", ruimSoft: "#fdecec", info: "#12539f", infoSoft: "#eff5fe",
      },
      boxShadow: { card: "0 1px 2px rgba(15,23,42,.05), 0 1px 1px rgba(15,23,42,.03)" },
    },
  },
};
