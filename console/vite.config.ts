import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev sur 5173. On parle au backend (8700) en relatif, via proxy : les mêmes
// URL /api et /ws marchent telles quelles une fois le build servi par le backend.
// Si le backend est absent, le proxy renvoie une erreur et la console bascule
// sur le mock local (voir src/api/source.ts).
export default defineConfig({
  plugins: [react()],
  base: "./",
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8700",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://127.0.0.1:8700",
        ws: true,
      },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
