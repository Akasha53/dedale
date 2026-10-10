// Service worker de l'extension Dédale.
//
// Il ne lit que l'adresse des pages, jamais leur contenu. Deux mécanismes :
//
// 1. Des règles declarativeNetRequest, tirées de la liste de confiance, bloquent
//    dans Chrome lui-même, avant toute requête, les adresses qui contiennent le
//    nom de confiance, même déguisé (orbispay-verification.example,
//    0rbispay.example). L'extension affiche alors l'avertissement à la place.
// 2. Pour les autres sosies (une lettre d'écart, autre alphabet), l'adresse est
//    lue au début de la navigation et l'onglet part vers l'avertissement. Sur un
//    site très rapide, la page peut avoir commencé à se charger : l'avertissement
//    la remplace aussitôt.
//
// Sur « Continuer quand même », le seul nom de domaine part vers le backend
// Dédale. S'il ne répond pas, la page s'ouvre quand même et l'échec est noté pour
// la fenêtre de l'icône.

import { analyserDomaine, motifBlocage } from "./comparateur.js";
import { lireReglages } from "./reglages.js";

const VERSION = chrome.runtime.getManifest().version;
const DELAI_BACKEND_MS = 3000;
const COULEUR_BADGE = "#1f1f1f";
const PRIORITE = { blocage: 1, confiance: 2, choix: 3 };

// Les compteurs et la liste des domaines autorisés se lisent puis s'écrivent :
// une file évite que deux mises à jour simultanées s'écrasent.
let file = Promise.resolve();
function enFile(tache) {
  const suite = file.then(tache, tache);
  file = suite.catch(() => {});
  return suite;
}

// Événements d'un même onglet traités l'un après l'autre : le début de navigation
// et le blocage d'un même sosie ne produisent qu'un avertissement.
const filesOnglets = new Map();
function parOnglet(tabId, tache) {
  const suite = (filesOnglets.get(tabId) ?? Promise.resolve()).then(tache, tache);
  filesOnglets.set(tabId, suite.catch(() => {}));
  return suite;
}

const enCours = new Map(); // tabId → { domaine, t } : avertissement en train de s'ouvrir
const retours = new Map(); // tabId → { domaine, echeance } : la personne recule depuis un avertissement

// ---------------------------------------------------------------- réglages en mémoire

let cache = null;
function reglages() {
  cache ??= lireReglages();
  return cache;
}

chrome.storage.onChanged.addListener((changements, zone) => {
  if (zone === "local" && changements.reglages) {
    cache = null;
    majReglesBlocage().catch((e) => console.warn("Dédale, règles :", e));
  }
});

// ---------------------------------------------------------------- règles declarativeNetRequest

async function majReglesBlocage() {
  const { domaines } = await reglages();
  const regles = [];
  for (const domaine of domaines) {
    regles.push({
      id: regles.length + 1,
      priority: PRIORITE.confiance,
      action: { type: "allow" },
      condition: { requestDomains: [domaine], resourceTypes: ["main_frame"] },
    });
    const motif = motifBlocage(domaine);
    if (!motif) continue;
    const { isSupported } = await chrome.declarativeNetRequest.isRegexSupported({ regex: motif });
    if (!isSupported) continue;
    regles.push({
      id: regles.length + 1,
      priority: PRIORITE.blocage,
      action: { type: "block" },
      condition: { regexFilter: motif, isUrlFilterCaseSensitive: false, resourceTypes: ["main_frame"] },
    });
  }
  const anciennes = await chrome.declarativeNetRequest.getDynamicRules();
  await chrome.declarativeNetRequest.updateDynamicRules({
    removeRuleIds: anciennes.map((r) => r.id),
    addRules: regles,
  });
}

// Domaines que la personne a choisi d'ouvrir malgré l'avertissement, jusqu'à la
// fermeture du navigateur : une règle d'autorisation de session les laisse passer.
async function domainesAutorises() {
  const { autorises } = await chrome.storage.session.get("autorises");
  return Array.isArray(autorises) ? autorises : [];
}

function autoriser(domaine) {
  return enFile(async () => {
    const autorises = await domainesAutorises();
    if (autorises.includes(domaine)) return;
    autorises.push(domaine);
    await chrome.storage.session.set({ autorises });
    const existantes = await chrome.declarativeNetRequest.getSessionRules();
    const id = Math.max(0, ...existantes.map((r) => r.id)) + 1;
    await chrome.declarativeNetRequest.updateSessionRules({
      addRules: [{
        id,
        priority: PRIORITE.choix,
        action: { type: "allow" },
        condition: { requestDomains: [domaine], resourceTypes: ["main_frame"] },
      }],
    });
  });
}

// ---------------------------------------------------------------- compteurs et badge

async function lireCompteurs() {
  const { compteurs } = await chrome.storage.local.get("compteurs");
  return { affiches: 0, passes: 0, ...(compteurs ?? {}) };
}

function evites(c) {
  return Math.max(0, c.affiches - c.passes);
}

function incrementer(cle) {
  return enFile(async () => {
    const c = await lireCompteurs();
    c[cle] += 1;
    await chrome.storage.local.set({ compteurs: c });
    await majBadge(c);
  });
}

async function majBadge(c) {
  const n = evites(c ?? (await lireCompteurs()));
  await chrome.action.setBadgeBackgroundColor({ color: COULEUR_BADGE });
  if (chrome.action.setBadgeTextColor) await chrome.action.setBadgeTextColor({ color: "#ffffff" });
  await chrome.action.setBadgeText({ text: n > 0 ? String(n) : "" });
}

// ---------------------------------------------------------------- navigation

function adresseWeb(adresse) {
  try {
    const url = new URL(adresse);
    return url.protocol === "http:" || url.protocol === "https:" ? url : null;
  } catch {
    return null;
  }
}

async function reculer(tabId) {
  await chrome.tabs.goBack(tabId).catch(() => chrome.tabs.update(tabId, { url: "chrome://newtab/" }));
}

/**
 * etape : « debut » (navigation demandée), « bloque » (Chrome a bloqué la
 * requête par une règle), « valide » (la page a commencé à s'afficher).
 */
async function examiner(tabId, adresse, etape) {
  const url = adresseWeb(adresse);
  if (!url || tabId < 0) return;
  const { domaines, nom } = await reglages();
  const r = analyserDomaine(url.hostname, domaines);

  const retour = retours.get(tabId);
  const recule = retour && retour.domaine === r.domaine && retour.echeance > Date.now();
  if (etape === "valide" && !recule) retours.delete(tabId); // arrivée ailleurs que sur ce sosie

  if (r.verdict !== "sosie") return;
  if ((await domainesAutorises()).includes(r.domaine)) return;

  // Retour arrière depuis l'avertissement vers une entrée d'historique de ce même
  // sosie : on recule d'un cran de plus au lieu d'avertir une seconde fois.
  if (recule) {
    if (etape !== "debut") await reculer(tabId);
    return;
  }

  const ouvert = enCours.get(tabId);
  if (ouvert && ouvert.domaine === r.domaine && Date.now() - ouvert.t < 5000) return;
  enCours.set(tabId, { domaine: r.domaine, t: Date.now() });

  const id = crypto.randomUUID();
  // L'adresse complète reste dans la session du navigateur : elle sert seulement
  // à rouvrir la page si la personne choisit de continuer.
  await chrome.storage.session.set({
    ["avert:" + id]: {
      id, tabId, url: adresse, nom,
      domaine: r.domaine, affiche: r.affiche, imite: r.imite,
      raison: r.raison, explication: r.explication,
    },
  });
  await chrome.tabs.update(tabId, { url: chrome.runtime.getURL(`avertissement.html#${id}`) });
  await incrementer("affiches");
}

function surveiller(etape) {
  return (d) => {
    if (d.frameId !== 0) return;
    parOnglet(d.tabId, () => examiner(d.tabId, d.url, etape))
      .catch((e) => console.warn("Dédale, navigation :", e));
  };
}

chrome.webNavigation.onBeforeNavigate.addListener((d) => {
  // Une page préchargée en arrière-plan n'est pas affichée : elle sera examinée
  // au moment où elle s'affiche.
  if (d.documentLifecycle === "prerender") return;
  surveiller("debut")(d);
});
chrome.webNavigation.onCommitted.addListener(surveiller("valide"));
chrome.webNavigation.onErrorOccurred.addListener((d) => {
  if (String(d.error).includes("ERR_BLOCKED_BY_CLIENT")) surveiller("bloque")(d);
});

chrome.tabs.onRemoved.addListener((tabId) => {
  enCours.delete(tabId);
  retours.delete(tabId);
  filesOnglets.delete(tabId);
});

// ---------------------------------------------------------------- backend Dédale

async function idSession() {
  let { sessionId } = await chrome.storage.local.get("sessionId");
  if (!sessionId) {
    sessionId = `navigateur-${crypto.randomUUID().slice(0, 8)}`;
    await chrome.storage.local.set({ sessionId });
  }
  return sessionId;
}

/**
 * Prévient le backend qu'un salarié a continué vers un sosie. Le corps suit le
 * schéma « avertissement » du pilier humain (CONTRATS.md) et ne porte que le nom
 * de domaine. Ne lève jamais d'erreur.
 */
async function signaler(domaine) {
  const { backend } = await reglages();
  const corps = {
    horodatage: new Date().toISOString(),
    source: "humain",
    surface: "poste",
    type: "avertissement",
    session_id: await idSession(),
    user_agent: `dedale-extension/${VERSION}`,
    details: { categorie: "phishing", choix: "continuer", contexte: "navigation", cible: domaine },
  };
  const minuterie = new AbortController();
  const delai = setTimeout(() => minuterie.abort(), DELAI_BACKEND_MS);
  let etat;
  try {
    const rep = await fetch(`${backend}/api/evenements`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corps),
      signal: minuterie.signal,
      credentials: "omit",
    });
    etat = rep.ok ? "recu" : `refuse_${rep.status}`;
  } catch {
    etat = "injoignable";
  } finally {
    clearTimeout(delai);
  }
  await chrome.storage.local.set({ dernierSignalement: { heure: Date.now(), domaine, etat } });
  return etat;
}

// ---------------------------------------------------------------- messages des pages

async function lireAvertissement(id) {
  const cle = "avert:" + id;
  const { [cle]: a } = await chrome.storage.session.get(cle);
  return a ?? null;
}

async function traiter(msg, expediteur) {
  const tabId = expediteur.tab?.id;
  switch (msg?.type) {
    case "avertissement": {
      enCours.delete(tabId); // affiché : une nouvelle visite du sosie sera avertie
      const a = await lireAvertissement(msg.id);
      if (!a) return { trouve: false };
      const { nom, domaine, affiche, imite, explication } = a;
      return { trouve: true, nom, domaine, affiche, imite, explication };
    }

    case "continuer": {
      const a = await lireAvertissement(msg.id);
      if (!a) return { url: null };
      await autoriser(a.domaine);
      await chrome.storage.session.remove("avert:" + msg.id);
      await incrementer("passes");
      // Envoi sans attendre : la page s'ouvre tout de suite, backend présent ou non.
      signaler(a.domaine).catch(() => {});
      return { url: a.url };
    }

    case "revenir": {
      const a = await lireAvertissement(msg.id);
      await chrome.storage.session.remove("avert:" + msg.id);
      if (tabId === undefined) return { ok: false };
      if (msg.historique) {
        if (a) retours.set(tabId, { domaine: a.domaine, echeance: Date.now() + 5000 });
      } else {
        await chrome.tabs.update(tabId, { url: "chrome://newtab/" });
      }
      return { ok: true };
    }

    case "etat": {
      const c = await lireCompteurs();
      const { dernierSignalement = null } = await chrome.storage.local.get("dernierSignalement");
      return { evites: evites(c), passes: c.passes, affiches: c.affiches, dernierSignalement };
    }

    case "remise_a_zero":
      await enFile(async () => {
        await chrome.storage.local.set({ compteurs: { affiches: 0, passes: 0 } });
        await majBadge({ affiches: 0, passes: 0 });
      });
      return { ok: true };

    default:
      return { erreur: "message inconnu" };
  }
}

chrome.runtime.onMessage.addListener((msg, expediteur, repondre) => {
  if (expediteur.id !== chrome.runtime.id) return false;
  traiter(msg, expediteur).then(repondre, (e) => repondre({ erreur: String(e?.message ?? e) }));
  return true;
});

// ---------------------------------------------------------------- démarrage

chrome.runtime.onInstalled.addListener(() => {
  idSession().catch(() => {});
});
majReglesBlocage().catch((e) => console.warn("Dédale, règles :", e));
majBadge().catch(() => {});
