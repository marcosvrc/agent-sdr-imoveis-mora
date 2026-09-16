import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  // No docker compose (bind mount no Mac/Windows) os eventos de arquivo não chegam: usar polling.
  server: { host: true, watch: { usePolling: process.env.CHOKIDAR_USEPOLLING === "true", interval: 500 } },
  build: {
    rollupOptions: {
      output: {
        // Separar o vendor do código do site: o React muda de versão uma vez por ano, o site muda
        // toda semana — com um chunk só, cada deploy invalidava 250 kB de cache do visitante.
        manualChunks: { vendor: ["react", "react-dom", "react-router-dom", "@tanstack/react-query"] },
      },
    },
  },
  plugins: [react(), VitePWA({
    registerType: "autoUpdate",
    manifest: {
      name: "Vértice Imóveis",
      short_name: "Vértice",
      description: "Imóveis em São Paulo com atendimento imediato pela Mora.",
      lang: "pt-BR",
      theme_color: "#0f172a",
      background_color: "#fbfaf7",
      display: "standalone",
      start_url: "/",
      // Antes: icons: [] — manifest inválido, instalação recusada pelo navegador sem dizer por quê.
      icons: [
        { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
        { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
        { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
      ],
    },
  })],
});
