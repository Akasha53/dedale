import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev sur 5173. On parle au backend (8700) en relatif, via proxy : les mêmes
// URL /api et /ws marchent telles quelles une fois le build servi par le backend.
// Si le backend est absent, le proxy renvoie une erreur et la console bascule
// sur le mock local (voir src/api/source.ts).
// DEDALE_BACKEND pointe le proxy vers un autre backend (ex. une base de test sur
// un autre port) sans toucher au 8700 partagé.
declare const process: { env: Record<string, string | undefined> };
const BACKEND = (process.env.DEDALE_BACKEND || "http://127.0.0.1:8700").replace(/\/$/, "");

export default defineConfig({
  plugins: [react()],
  base: "./",
  server: {
    port: 5173,
    strictPort: true,
    // Les jetons communs à la console et à la landing vivent dans ../design.
    fs: {
      allow: [".", "../design"],
    },
    proxy: {
      "/api": {
        target: BACKEND,
        changeOrigin: true,
      },
      "/ws": {
        target: BACKEND.replace(/^http/, "ws"),
        ws: true,
      },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
