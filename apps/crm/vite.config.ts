import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Porta 3000 é a que a especificação documenta para o painel (seção 12).
export default defineConfig({ plugins: [react()], server: { port: 3000, host: true } });
