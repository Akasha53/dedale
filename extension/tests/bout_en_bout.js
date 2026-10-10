// Vérification de bout en bout, sans rien toucher au système.
//
//   node tests/bout_en_bout.js [--captures <dossier>]
//
// Lance, sur des ports libres et dans un dossier temporaire :
//   - un backend Dédale ISOLÉ (DEDALE_DB temporaire, jamais le port 8700) ;
//   - un faux site local qui répond pour tous les domaines en .example ;
//   - Chrome sans fenêtre, sur un profil temporaire, avec l'extension non
//     empaquetée. --host-resolver-rules envoie *.example vers le faux site :
//     pas de /etc/hosts, et l'extension voit le vrai nom de domaine.
// Puis visite un domaine neutre, le vrai domaine et quatre sosies, clique sur les
// deux boutons et vérifie ce qui arrive au backend.
//
// Chrome stable ignore --load-extension depuis la version 137 : l'extension est
// chargée par le canal CDP officiel (Extensions.loadUnpacked). Variable CHROME
// pour choisir un autre binaire.

import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdtempSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import net from "node:net";
import { homedir, tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ICI = path.dirname(fileURLToPath(import.meta.url));
const EXTENSION = path.resolve(ICI, "..");
const BACKEND = path.resolve(EXTENSION, "..", "backend");
const TEMP = mkdtempSync(path.join(tmpdir(), "dedale-extension-"));
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

function portLibre() {
  return new Promise((ok, ko) => {
    const s = net.createServer();
    s.once("error", ko);
    s.listen(0, "127.0.0.1", () => {
      const { port } = s.address();
      s.close(() => ok(port));
    });
  });
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

// Charge l'extension par le canal CDP « pipe » (descripteurs 3 et 4), la seule
// voie que Chrome stable accepte encore : il ignore --load-extension depuis la
// version 137. Messages JSON séparés par un octet nul.
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

// Identifiant d'une extension non empaquetée : SHA-256 du chemin, 32 premiers
// chiffres hexadécimaux transposés de 0-f vers a-p.
function idExtension(chemin) {
  return [...createHash("sha256").update(chemin).digest("hex").slice(0, 32)]
    .map((c) => String.fromCharCode(97 + parseInt(c, 16))).join("");
}

// ---------------------------------------------------------------- CDP minimal

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

  async aller(url) {
    await this.cmd("Page.navigate", { url });
  }

  adresse() {
    return this.eval("location.href");
  }

  async capture(nom) {
    if (!CAPTURES) return;
    const { data } = await this.cmd("Page.captureScreenshot", { format: "png" });
    const fichier = path.join(CAPTURES, nom);
    writeFileSync(fichier, Buffer.from(data, "base64"));
    console.log(`     capture : ${fichier}`);
  }

  fermer() {
    this.ws.close();
  }
}

// ---------------------------------------------------------------- scénario

async function principal() {
  const [pBackend, pSite, pCdp, pFerme] = await Promise.all([portLibre(), portLibre(), portLibre(), portLibre()]);
  if (pBackend === 8700) throw new Error("le port 8700 est réservé au vrai backend");
  console.log(`dossier temporaire : ${TEMP}`);
  console.log(`backend isolé : 127.0.0.1:${pBackend}, faux site : ${pSite}, CDP : ${pCdp}`);

  // 1. Backend isolé.
  const backend = spawn("uv", ["run", "--quiet", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(pBackend)], {
    cwd: BACKEND,
    env: { ...process.env, DEDALE_DB: path.join(TEMP, "dedale.db"), DEDALE_LLM: "off" },
    stdio: ["ignore", "ignore", "pipe"],
  });
  processus.push(backend);
  let journalBackend = "";
  backend.stderr.on("data", (d) => { journalBackend += d; });
  const urlBackend = `http://127.0.0.1:${pBackend}`;
  await attendre(async () => (await fetch(`${urlBackend}/api/sante`)).ok, "backend isolé", 90000)
    .catch((e) => { console.error(journalBackend.slice(-2000)); throw e; });

  // 2. Faux site : répond pour tout domaine en .example et note chaque requête.
  const visites = [];
  const site = createServer((req, res) => {
    visites.push(`${req.headers.host}${req.url}`);
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    res.end(`<!doctype html><title>Page de test ${req.headers.host}</title><h1>Page de test servie pour ${req.headers.host}</h1>`);
  });
  await new Promise((ok) => site.listen(pSite, "127.0.0.1", ok));

  // 3. Chrome sans fenêtre, profil temporaire, extension chargée.
  const chrome = spawn(trouverChrome(), [
    `--user-data-dir=${path.join(TEMP, "profil")}`,
    "--remote-debugging-pipe",
    "--enable-unsafe-extension-debugging",
    `--remote-debugging-port=${pCdp}`,
    "--host-resolver-rules=MAP *.example 127.0.0.1",
    "--headless=new",
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

  // Réglages : le backend isolé à la place de 127.0.0.1:8700.
  const reglages = await Onglet.ouvrir(pCdp, `chrome-extension://${id}/options.html`);
  await attendre(() => reglages.eval("document.readyState === 'complete'"), "page d'options");
  await reglages.eval(`chrome.storage.local.set({ reglages: { nom: "Orbis Pay", domaines: ["orbispay.example"], backend: "${urlBackend}" } })`);
  const etat = () => reglages.eval(`chrome.runtime.sendMessage({ type: "etat" })`);

  const onglet = await Onglet.ouvrir(pCdp);
  const port = `:${pSite}`;
  const surAvertissement = async () => (await onglet.adresse()).startsWith(`chrome-extension://${id}/avertissement.html`);
  const texte = (sel) => onglet.eval(`document.querySelector(${JSON.stringify(sel)})?.textContent?.trim() ?? null`);

  // 4. Domaine neutre puis vrai domaine : aucun avertissement.
  await onglet.aller(`http://fleuriste.example${port}/`);
  await attendre(async () => (await onglet.eval("document.title")).includes("fleuriste.example"), "site neutre");
  verifier(!(await surAvertissement()), "domaine neutre ouvert sans avertissement", "fleuriste.example");

  await onglet.aller(`http://orbispay.example${port}/accueil`);
  await attendre(async () => (await onglet.eval("document.title")).includes("orbispay.example"), "vrai site");
  verifier(!(await surAvertissement()), "domaine de confiance ouvert sans avertissement", "orbispay.example");

  // 5. Sosie : l'avertissement remplace la page.
  const sosie = `http://orbispay-verification.example${port}/chemin-prive-xq7?jeton=zz9`;
  await onglet.aller(sosie);
  await attendre(surAvertissement, "page d'avertissement");
  await attendre(async () => (await texte("#domaine")) === "orbispay-verification.example", "domaine affiché");
  const titre = await onglet.eval(`document.querySelector("h1").innerText.replace(/\\s+/g, " ").trim()`);
  verifier(titre === "Ce site imite Orbis Pay. Ce n'est pas le vrai site.", "titre de l'avertissement", titre);
  verifier((await texte("#vrai")) === "orbispay.example", "vrai site rappelé");
  verifier((await onglet.eval("document.activeElement?.id")) === "revenir", "« Revenir en arrière » a le focus");
  verifier(!visites.some((v) => v.startsWith("orbispay-verification.example")),
    "aucune requête partie vers le sosie avant le choix", "bloquée par la règle declarativeNetRequest");
  for (const theme of ["light", "dark"]) {
    await onglet.cmd("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: theme }] });
    await pause(400); // fin des transitions de couleur
    await onglet.capture(`avertissement-${theme === "light" ? "clair" : "sombre"}.png`);
  }
  await onglet.cmd("Emulation.setEmulatedMedia", { features: [] });

  // 6. « Revenir en arrière » : retour au vrai site, compteur à 1, rien envoyé.
  await onglet.eval(`document.getElementById("revenir").click()`);
  await attendre(async () => (await onglet.adresse()).includes("orbispay.example"), "retour arrière");
  verifier((await onglet.adresse()) === `http://orbispay.example${port}/accueil`, "retour à la page précédente");
  const apresRetour = await etat();
  verifier(apresRetour.evites === 1 && apresRetour.passes === 0, "compteur : 1 sosie évité", JSON.stringify(apresRetour));
  verifier(apresRetour.dernierSignalement === null, "aucun envoi au backend sur un retour arrière");

  // 7. « Continuer quand même » : la page s'ouvre, le backend reçoit le domaine seul.
  await onglet.aller(sosie);
  await attendre(surAvertissement, "page d'avertissement (2)");
  await attendre(async () => (await texte("#domaine")) === "orbispay-verification.example", "domaine affiché (2)");
  await onglet.eval(`document.getElementById("continuer").click()`);
  await attendre(async () => (await onglet.adresse()) === sosie, "ouverture du sosie après accord");
  verifier(true, "« Continuer quand même » ouvre la page demandée", sosie);

  const incident = await attendre(async () => {
    const { incidents } = await (await fetch(`${urlBackend}/api/incidents`)).json();
    return incidents.find((i) => i.type === "humain_phishing");
  }, "incident humain_phishing au backend");
  verifier(true, "incident ouvert par le backend isolé", `${incident.id}, ${incident.type}, gravité ${incident.gravite}`);

  const sessionId = incident.session_id ?? incident.session?.id;
  const session = await (await fetch(`${urlBackend}/api/sessions/${encodeURIComponent(sessionId)}`)).json();
  const evenements = session.evenements ?? [];
  const ev = evenements.find((e) => e.type === "avertissement");
  verifier(Boolean(ev), "événement « avertissement » enregistré", sessionId);
  if (ev) {
    verifier(ev.source === "humain" && ev.surface === "poste", "source humain, surface poste");
    verifier(JSON.stringify(Object.keys(ev.details).sort()) === JSON.stringify(["categorie", "choix", "cible", "contexte"]),
      "details limités à categorie, choix, contexte, cible", JSON.stringify(ev.details));
    verifier(ev.details.categorie === "phishing" && ev.details.choix === "continuer" && ev.details.contexte === "navigation",
      "catégorie phishing, choix continuer, contexte navigation");
    verifier(String(ev.details.cible).includes("orbispay-verification.example"), "cible : le domaine visité", ev.details.cible);
  }
  const tout = JSON.stringify(session) + JSON.stringify(incident);
  verifier(!tout.includes("chemin-prive-xq7") && !tout.includes("zz9"), "ni chemin ni paramètres envoyés au backend");
  const apresContinuer = await etat();
  verifier(apresContinuer.dernierSignalement?.etat === "recu", "signalement reçu par Dédale", apresContinuer.dernierSignalement?.etat);

  // 8. Alphabet étranger : le domaine s'affiche tel que l'œil le lit, et en punycode.
  await onglet.aller(`http://xn--rbispay-8ig.example${port}/`);
  await attendre(surAvertissement, "avertissement punycode");
  await attendre(async () => (await texte("#domaine")) === "оrbispay.example", "domaine Unicode affiché");
  verifier((await texte("#reel")) === "Adresse réelle : xn--rbispay-8ig.example", "adresse réelle en punycode affichée");
  await onglet.capture("avertissement-punycode.png");
  await onglet.eval(`document.getElementById("revenir").click()`);
  await attendre(async () => !(await surAvertissement()), "retour arrière (punycode)");
  verifier((await onglet.adresse()) === sosie, "retour arrière vers la page précédente (punycode)", await onglet.adresse());

  // 8 bis. Domaine qui n'existe nulle part (.invalid) : la règle bloque avant le DNS.
  await onglet.aller("http://orbispay-securite.invalid/");
  await attendre(surAvertissement, "avertissement sans serveur");
  await attendre(async () => (await texte("#domaine")) === "orbispay-securite.invalid", "domaine affiché (.invalid)");
  verifier(true, "avertissement affiché pour un domaine qui ne résout pas", "orbispay-securite.invalid");
  await onglet.eval(`document.getElementById("revenir").click()`);
  await attendre(async () => !(await surAvertissement()), "retour arrière (.invalid)");

  // 9. Backend absent : la navigation continue, l'échec est seulement noté.
  await reglages.eval(`chrome.storage.local.set({ reglages: { nom: "Orbis Pay", domaines: ["orbispay.example"], backend: "http://127.0.0.1:${pFerme}" } })`);
  const sosie2 = `http://0rbispay.example${port}/`;
  await onglet.aller(sosie2);
  await attendre(surAvertissement, "avertissement sans backend");
  await attendre(async () => (await texte("#domaine")) === "0rbispay.example", "domaine affiché (3)");
  await onglet.eval(`document.getElementById("continuer").click()`);
  await attendre(async () => (await onglet.adresse()) === sosie2, "ouverture du sosie sans backend");
  const sansBackend = await attendre(async () => {
    const e = await etat();
    return e.dernierSignalement?.domaine === "0rbispay.example" ? e : null;
  }, "signalement noté sans backend");
  verifier(sansBackend.dernierSignalement.etat === "injoignable", "backend absent : page ouverte, échec noté sans planter",
    sansBackend.dernierSignalement.etat);

  // 10. Compteur et badge de l'icône.
  const fin = await etat();
  const badge = await reglages.eval("chrome.action.getBadgeText({})");
  verifier(fin.affiches === 5 && fin.passes === 2 && fin.evites === 3, "compteurs : 5 avertissements, 2 ignorés, 3 évités", JSON.stringify(fin));
  verifier(badge === "3", "badge de l'icône", badge);

  // Captures de la fenêtre de l'icône et des réglages.
  const popup = await Onglet.ouvrir(pCdp, `chrome-extension://${id}/popup.html`);
  await attendre(async () => (await popup.eval(`document.getElementById("evites").textContent`)) === "3", "fenêtre de l'icône");
  await popup.cmd("Emulation.setDeviceMetricsOverride", { width: 332, height: 300, deviceScaleFactor: 2, mobile: false });
  await popup.cmd("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: "light" }] });
  await pause(400);
  await popup.capture("icone.png");
  await reglages.cmd("Page.reload");
  await attendre(() => reglages.eval(`document.getElementById("backend").value.includes("${pFerme}")`), "réglages rechargés");
  await reglages.eval(`(() => { const e = document.getElementById("essai"); e.value = "orbis-pay.example"; e.dispatchEvent(new Event("input")); })()`);
  await reglages.capture("reglages.png");

  console.log(`requêtes reçues par le faux site : ${visites.join(", ")}`);
  [onglet, reglages, popup].forEach((o) => o.fermer());
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
