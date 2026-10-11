// Vérification du parcours d'hameçonnage de démonstration, sans rien toucher au
// système.
//
//   node tests/demo_hameconnage.js [--captures <dossier>]
//
// Lance Chrome sans fenêtre sur un profil temporaire, charge l'extension non
// empaquetée, allume le mode démonstration, puis :
//   - clique le lien piégé « orbispay.example/connexion » (un domaine qui ne
//     résout nulle part) et vérifie que l'interstitiel s'affiche AVANT l'échec DNS ;
//   - suit « Continuer quand même » vers le faux site Orbis servi par l'extension
//     (bandeau « Exemple de faux site », formulaire inerte) ;
//   - suit « Me protéger » vers la page bloquée (compte à rebours, fermeture) ;
//   - vérifie qu'un sosie d'Orbis ouvre aussi l'interstitiel ;
//   - éteint le mode et vérifie que le comportement d'origine revient.
//
// Aucun serveur, aucun réseau : toutes les pages du parcours sont servies par
// l'extension. Chrome stable ignore --load-extension depuis la version 137 :
// l'extension est chargée par le canal CDP (Extensions.loadUnpacked). Variable
// CHROME pour choisir un autre binaire.

import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdtempSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ICI = path.dirname(fileURLToPath(import.meta.url));
const EXTENSION = path.resolve(ICI, "..");
const TEMP = mkdtempSync(path.join(tmpdir(), "dedale-demo-"));
const iCaptures = process.argv.indexOf("--captures");
const CAPTURES = iCaptures > 0 ? path.resolve(process.argv[iCaptures + 1]) : null;

const processus = [];
const resultats = [];
let echecs = 0;

function verifier(condition, libelle, detail = "") {
  resultats.push(`${condition ? "ok  " : "ÉCHEC"} ${libelle}${detail ? ` (${detail})` : ""}`);
  if (!condition) echecs += 1;
  console.log(resultats.at(-1));
}

const pause = (ms) => new Promise((r) => setTimeout(r, ms));

async function attendre(fn, libelle, delai = 15000) {
  const fin = Date.now() + delai;
  let dernier;
  while (Date.now() < fin) {
    try {
      dernier = await fn();
      if (dernier) return dernier;
    } catch (e) {
      dernier = e;
    }
    await pause(150);
  }
  throw new Error(`délai dépassé : ${libelle} (${dernier?.message ?? dernier})`);
}

function trouverChrome() {
  if (process.env.CHROME) return process.env.CHROME;
  const candidats = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
  ];
  for (const cache of [path.join(homedir(), "Library/Caches/ms-playwright"), path.join(homedir(), ".cache/ms-playwright")]) {
    if (!existsSync(cache)) continue;
    for (const v of readdirSync(cache).filter((d) => /^chromium-\d+$/.test(d)).sort().reverse()) {
      candidats.push(
        path.join(cache, v, "chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"),
        path.join(cache, v, "chrome-linux/chrome"),
      );
    }
  }
  const trouve = candidats.find((p) => existsSync(p));
  if (!trouve) throw new Error("Chrome introuvable : indiquez son chemin dans la variable CHROME.");
  return trouve;
}

function chargerExtension(chrome) {
  return new Promise((ok, ko) => {
    let tampon = "";
    const minuterie = setTimeout(() => ko(new Error("Extensions.loadUnpacked sans réponse")), 15000);
    chrome.stdio[4].on("data", (morceau) => {
      tampon += morceau.toString("utf8");
      let i;
      while ((i = tampon.indexOf("\0")) >= 0) {
        const msg = JSON.parse(tampon.slice(0, i));
        tampon = tampon.slice(i + 1);
        if (msg.id !== 1) continue;
        clearTimeout(minuterie);
        msg.error ? ko(new Error(msg.error.message)) : ok(msg.result.id);
      }
    });
    chrome.stdio[3].write(JSON.stringify({ id: 1, method: "Extensions.loadUnpacked", params: { path: EXTENSION } }) + "\0");
  });
}

function idExtension(chemin) {
  return [...createHash("sha256").update(chemin).digest("hex").slice(0, 32)]
    .map((c) => String.fromCharCode(97 + parseInt(c, 16))).join("");
}

class Onglet {
  constructor(ws) {
    this.ws = ws;
    this.n = 0;
    this.attente = new Map();
    ws.addEventListener("message", (m) => {
      const msg = JSON.parse(m.data);
      const p = this.attente.get(msg.id);
      if (!p) return;
      this.attente.delete(msg.id);
      msg.error ? p.ko(new Error(msg.error.message)) : p.ok(msg.result);
    });
  }

  static async ouvrir(portCdp, url = "about:blank") {
    const rep = await fetch(`http://127.0.0.1:${portCdp}/json/new?${encodeURI(url)}`, { method: "PUT" });
    const cible = await rep.json();
    const ws = new WebSocket(cible.webSocketDebuggerUrl);
    await new Promise((ok, ko) => { ws.onopen = ok; ws.onerror = ko; });
    const o = new Onglet(ws);
    await o.cmd("Page.enable");
    return o;
  }

  cmd(method, params = {}, delai = 10000) {
    const id = ++this.n;
    this.ws.send(JSON.stringify({ id, method, params }));
    return new Promise((ok, ko) => {
      const minuterie = setTimeout(() => {
        this.attente.delete(id);
        ko(new Error(`pas de réponse à ${method}`));
      }, delai);
      this.attente.set(id, {
        ok: (v) => { clearTimeout(minuterie); ok(v); },
        ko: (e) => { clearTimeout(minuterie); ko(e); },
      });
    });
  }

  async eval(expression) {
    const r = await this.cmd("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? "erreur de script");
    return r.result.value;
  }

  async aller(url) { await this.cmd("Page.navigate", { url }); }
  adresse() { return this.eval("location.href"); }

  async capture(nom) {
    if (!CAPTURES) return;
    const { data } = await this.cmd("Page.captureScreenshot", { format: "png" });
    const fichier = path.join(CAPTURES, nom);
    writeFileSync(fichier, Buffer.from(data, "base64"));
    console.log(`     capture : ${fichier}`);
  }

  fermer() { this.ws.close(); }
}

function portLibre() {
  return import("node:net").then(({ default: net }) => new Promise((ok, ko) => {
    const s = net.createServer();
    s.once("error", ko);
    s.listen(0, "127.0.0.1", () => {
      const { port } = s.address();
      s.close(() => ok(port));
    });
  }));
}

async function principal() {
  const pCdp = await portLibre();
  console.log(`dossier temporaire : ${TEMP}, CDP : ${pCdp}`);

  const chrome = spawn(trouverChrome(), [
    `--user-data-dir=${path.join(TEMP, "profil")}`,
    "--remote-debugging-pipe",
    "--enable-unsafe-extension-debugging",
    `--remote-debugging-port=${pCdp}`,
    "--headless=new",
    "--use-mock-keychain",
    "--password-store=basic",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-features=HttpsUpgrades",
    "--window-size=1100,820",
    "about:blank",
  ], { stdio: ["ignore", "ignore", "ignore", "pipe", "pipe"] });
  processus.push(chrome);
  await attendre(async () => (await fetch(`http://127.0.0.1:${pCdp}/json/version`)).ok, "Chrome");

  const id = await chargerExtension(chrome);
  verifier(id === idExtension(EXTENSION), "extension chargée depuis le dossier", id);
  const sw = await attendre(async () => {
    const liste = await (await fetch(`http://127.0.0.1:${pCdp}/json/list`)).json();
    return liste.find((c) => c.type === "service_worker" && c.url === `chrome-extension://${id}/service_worker.js`);
  }, "service worker de l'extension");
  verifier(Boolean(sw), "service worker actif", sw.url);

  const base = `chrome-extension://${id}`;
  const interstitiel = `${base}/demo/interstitiel.html`;

  // Réglages Orbis Pay + mode démonstration allumé.
  const reglages = await Onglet.ouvrir(pCdp, `${base}/options.html`);
  await attendre(() => reglages.eval("document.readyState === 'complete'"), "page d'options");
  await reglages.eval(`chrome.storage.local.set({ reglages: { nom: "Orbis Pay", domaines: ["orbispay.example"] }, demo: true })`);

  const onglet = await Onglet.ouvrir(pCdp);
  const texte = (sel) => onglet.eval(`document.querySelector(${JSON.stringify(sel)})?.textContent?.trim() ?? null`);
  const surInterstitiel = async () => (await onglet.adresse()).startsWith(interstitiel);

  // 1. Lien piégé sur le vrai domaine : intercepté avant l'échec DNS (.example ne
  //    résout nulle part, aucun serveur ici).
  await onglet.aller("http://orbispay.example/connexion");
  await attendre(surInterstitiel, "interstitiel sur le lien piégé");
  verifier(await surInterstitiel(), "lien piégé intercepté avant l'échec DNS", await onglet.adresse());
  await attendre(async () => (await texte("#domaine")) === "orbispay.example", "domaine affiché");
  verifier((await texte("#domaine")) === "orbispay.example", "domaine visé affiché", await texte("#domaine"));
  verifier((await onglet.eval("document.activeElement?.id")) === "arreter", "« Me protéger » a le focus");
  for (const theme of ["light", "dark"]) {
    await onglet.cmd("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: theme }] });
    await pause(400);
    await onglet.capture(`demo-interstitiel-${theme === "light" ? "clair" : "sombre"}.png`);
  }
  await onglet.cmd("Emulation.setEmulatedMedia", { features: [] });

  // 2. « Continuer quand même » : faux site Orbis servi par l'extension.
  await onglet.eval(`document.getElementById("continuer").click()`);
  await attendre(async () => (await onglet.adresse()) === `${base}/demo/faux-orbis.html`, "faux site Orbis");
  verifier((await onglet.adresse()) === `${base}/demo/faux-orbis.html`, "« Continuer » ouvre le faux site servi par l'extension");
  verifier((await texte(".bandeau")).includes("Exemple de faux site"), "bandeau « faux site » affiché", await texte(".bandeau"));
  verifier((await onglet.eval(`!document.getElementById("form").getAttribute("action")`)), "formulaire sans action (inerte)");
  await onglet.eval(`document.getElementById("id").value = "test@exemple.fr"; document.getElementById("form").requestSubmit()`);
  await pause(300);
  verifier(!(await onglet.eval(`document.getElementById("note").hidden`)), "soumettre ne part nulle part, affiche la note pédagogique");
  verifier((await onglet.adresse()) === `${base}/demo/faux-orbis.html`, "aucune navigation à la soumission", await onglet.adresse());
  await onglet.capture("demo-faux-orbis.png");

  // 3. « Me protéger » : page bloquée, compte à rebours, fermeture.
  await onglet.aller("http://orbispay.example/connexion");
  await attendre(surInterstitiel, "interstitiel (2)");
  await onglet.eval(`document.getElementById("arreter").click()`);
  await attendre(async () => (await onglet.adresse()) === `${base}/demo/bloquee.html`, "page bloquée");
  verifier((await texte("#titre")) === "Page bloquée par sAIfe", "titre de la page bloquée", await texte("#titre"));
  verifier((await texte("#reste")) === "3", "compte à rebours démarré à 3", await texte("#reste"));
  await onglet.capture("demo-bloquee.png");
  // Au bout de 3 s, le script tente de fermer l'onglet. Un onglet ouvert par CDP
  // n'est pas fermable par window.close : on vérifie alors le repli manuel.
  let ferme = false;
  await attendre(async () => {
    try {
      const r = await onglet.eval(`({ reste: document.getElementById("reste").textContent, tentee: !!window.__saifeFermetureTentee, repli: !document.getElementById("repli").hidden })`);
      return r.tentee && r.reste === "0" && r.repli ? r : null;
    } catch {
      ferme = true; // l'onglet s'est fermé : window.close a réussi
      return { ferme: true };
    }
  }, "fermeture ou repli de la page bloquée", 8000);
  verifier(true, ferme ? "onglet fermé automatiquement" : "fermeture refusée : compte à rebours à 0 et repli « Fermer » affiché");

  // 4. Sosie d'Orbis Pay : l'interstitiel s'affiche aussi.
  if (ferme) { onglet.fermer(); }
  const onglet2 = ferme ? await Onglet.ouvrir(pCdp) : onglet;
  const texte2 = (sel) => onglet2.eval(`document.querySelector(${JSON.stringify(sel)})?.textContent?.trim() ?? null`);
  await onglet2.aller("http://orbispay-verification.example/");
  await attendre(async () => (await onglet2.adresse()).startsWith(interstitiel), "interstitiel sur un sosie");
  verifier((await onglet2.adresse()).startsWith(interstitiel), "sosie d'Orbis intercepté vers l'interstitiel");
  await attendre(async () => (await texte2("#domaine")) === "orbispay-verification.example", "sosie affiché dans l'interstitiel");
  verifier((await texte2("#domaine")) === "orbispay-verification.example", "sosie affiché", await texte2("#domaine"));

  // 5. Mode éteint : le comportement d'origine revient (avertissement standard
  //    pour le sosie, et aucun interstitiel de démonstration sur le vrai domaine).
  await reglages.eval(`chrome.storage.local.set({ demo: false })`);
  await pause(300);
  await onglet2.aller("http://orbispay.example/connexion");
  await pause(1500);
  verifier(!(await onglet2.adresse()).startsWith(interstitiel),
    "mode éteint : le lien piégé n'ouvre plus l'interstitiel de démonstration", await onglet2.adresse());
  await onglet2.aller("http://orbispay-verification.example/");
  await attendre(async () => (await onglet2.adresse()).startsWith(`${base}/avertissement.html`), "avertissement standard (mode éteint)");
  verifier((await onglet2.adresse()).startsWith(`${base}/avertissement.html`),
    "mode éteint : le sosie ouvre l'avertissement standard, pas la démonstration");

  [onglet2, reglages].forEach((o) => { try { o.fermer(); } catch {} });
}

function nettoyer(signal = "SIGTERM") {
  for (const p of processus) {
    try { p.kill(signal); } catch {}
  }
}

process.on("exit", () => nettoyer("SIGKILL"));
process.on("SIGINT", () => process.exit(130));

try {
  await principal();
} catch (e) {
  echecs += 1;
  console.error(`ÉCHEC : ${e.message}`);
} finally {
  nettoyer();
  await pause(1500);
  nettoyer("SIGKILL");
  rmSync(TEMP, { recursive: true, force: true });
  console.log(echecs ? `\n${echecs} échec(s).` : `\nTout est vert (${resultats.length} vérifications).`);
  process.exit(echecs ? 1 : 0);
}
