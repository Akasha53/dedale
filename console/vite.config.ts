import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
// La console n'embarque pas @types/node : ces modules de Node sont lus sans leurs types.
// @ts-ignore
import { readFileSync } from "node:fs";
// @ts-ignore
import { homedir } from "node:os";
// @ts-ignore
import { join } from "node:path";

// Dev sur 5173. On parle au backend (8700) en relatif, via proxy : les mêmes
// URL /api et /ws marchent telles quelles une fois le build servi par le backend.
// Si le backend est absent, le proxy renvoie une erreur et la console bascule
// sur le mock local (voir src/api/source.ts).
// DEDALE_BACKEND pointe le proxy vers un autre backend (ex. une base de test sur
// un autre port) sans toucher au 8700 partagé.
declare const process: { env: Record<string, string | undefined> };
const BACKEND = (process.env.DEDALE_BACKEND || "http://127.0.0.1:8700").replace(/\/$/, "");

// Jetons : le proxy les ajoute côté serveur, ils n'apparaissent jamais dans le
// JavaScript servi. Relus à chaque requête dans ~/.config/dedale/ (ou
// DEDALE_JETONS), où le backend les a tirés au premier démarrage.
const DOSSIER_JETONS = process.env.DEDALE_JETONS || join(homedir(), ".config", "dedale");
function lireJeton(role: string): string | null {
  try {
    return readFileSync(join(DOSSIER_JETONS, `jeton-${role}`), "utf8").trim() || null;
  } catch {
    return null;
  }
}

// Une session par espace, tirée au lancement de Vite et posée en cookie HttpOnly,
// SameSite=Strict, quand le navigateur ouvre la page : la console du SOC reçoit
// le jeton analyste, l'espace /validation le jeton validateur, jamais l'inverse.
// Le proxy ne signe que les requêtes qui portent la session de leur espace : un
// curl sur 5173 n'hérite d'aucun jeton. Un script qui présente le sien le garde.
function secret(): string {
  return Array.from(crypto.getRandomValues(new Uint8Array(32)), (o) =>
    o.toString(16).padStart(2, "0")
  ).join("");
}
const ESPACES = {
  console: { cookie: "dedale_console", secret: secret(), role: "analyste" },
  validation: { cookie: "dedale_validation", secret: secret(), role: "validateur" },
};
// Vite 5.4.11 ne filtre pas l'en-tête Host : sans ce filtre, une page tierce qui
// fait pointer son nom de domaine sur 127.0.0.1 (DNS rebinding) obtiendrait le cookie.
const HOTES = new Set(["localhost", "127.0.0.1"]);

type Requete = { url?: string; headers: Record<string, string | string[] | undefined> };
type Sortante = { setHeader(nom: string, valeur: string): void };

// Comparaison en temps constant : la durée ne dit pas combien de caractères concordent.
function egaux(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let ecart = 0;
  for (let i = 0; i < a.length; i++) ecart |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return ecart === 0;
}

function porteLaSession(req: Requete, espace: { cookie: string; secret: string }): boolean {
  const cookies = req.headers.cookie;
  for (const morceau of (typeof cookies === "string" ? cookies : "").split(";")) {
    const [nom, ...reste] = morceau.trim().split("=");
    if (nom === espace.cookie) return egaux(reste.join("="), espace.secret);
  }
  return false;
}

function hoteLocal(req: Requete): boolean {
  const hote = req.headers.host;
  return typeof hote === "string" && HOTES.has(hote.replace(/:\d+$/, ""));
}

function signer(proxyReq: Sortante, req: Requete) {
  if (req.headers.authorization || !hoteLocal(req)) return;
  // Une page d'une autre origine (un leurre sur 8701, par exemple) n'emprunte jamais un jeton.
  const origine = req.headers.origin;
  if (typeof origine === "string" && origine !== `http://${req.headers.host}`) return;
  const site = req.headers["sec-fetch-site"];
  if (typeof site === "string" && site !== "same-origin") return;
  const espace = (req.url ?? "").startsWith("/api/validation/") ? ESPACES.validation : ESPACES.console;
  if (!porteLaSession(req, espace)) return;
  const jeton = lireJeton(espace.role);
  if (jeton) proxyReq.setHeader("Authorization", `Bearer ${jeton}`);
}

// Ouverture d'une page (pas d'un script ni d'une image) : la session de son espace.
function estUnePage(req: Requete): boolean {
  const dest = req.headers["sec-fetch-dest"];
  if (typeof dest === "string") return dest === "document";
  const accept = req.headers.accept;
  return typeof accept === "string" && accept.includes("text/html");
}

const sessionConsole: Plugin = {
  name: "dedale-session-console",
  configureServer(server) {
    server.middlewares.use((req, res, next) => {
      const requete = req as Requete;
      if (!hoteLocal(requete)) {
        res.statusCode = 403;
        res.end("Hôte refusé : la console ne répond qu'à localhost et 127.0.0.1.");
        return;
      }
      const url = requete.url ?? "";
      if (!url.startsWith("/api") && !url.startsWith("/ws") && estUnePage(requete)) {
        const espace = url.startsWith("/validation") ? ESPACES.validation : ESPACES.console;
        res.setHeader("Set-Cookie", `${espace.cookie}=${espace.secret}; HttpOnly; SameSite=Strict; Path=/`);
      }
      next();
    });
  },
};

export default defineConfig({
  plugins: [react(), sessionConsole],
  base: "./",
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: BACKEND,
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on("proxyReq", signer);
        },
      },
      "/ws": {
        target: BACKEND.replace(/^http/, "ws"),
        ws: true,
        configure: (proxy) => {
          proxy.on("proxyReqWs", signer);
        },
      },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
