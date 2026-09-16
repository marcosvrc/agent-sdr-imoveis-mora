import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  // No docker compose (bind mount no Mac/Windows) os eventos de arquivo não chegam: usar polling.
  server: { host: true, watch: { usePolling: process.env.CHOKIDAR_USEPOLLING === "true", interval: 500 } },
  plugins: [react()],
});
