// Réglages de l'extension, rangés dans chrome.storage.local sous la clé « reglages ».
// Partagé par le service worker, la page d'options et la fenêtre de l'icône.

import { DOMAINES_PAR_DEFAUT, NOM_PAR_DEFAUT, normaliserHote } from "./comparateur.js";

export const BACKEND_PAR_DEFAUT = "http://127.0.0.1:8700";

export const REGLAGES_PAR_DEFAUT = Object.freeze({
  nom: NOM_PAR_DEFAUT,
  domaines: DOMAINES_PAR_DEFAUT,
  backend: BACKEND_PAR_DEFAUT,
});

/** Adresse http(s) sans barre finale, ou null si elle n'en est pas une. */
export function adresseBackend(texte) {
  try {
    const url = new URL(String(texte ?? "").trim());
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    if (url.username || url.password) return null;
    return (url.origin + url.pathname).replace(/\/+$/, "");
  } catch {
    return null;
  }
}

/** Origine d'une adresse de backend, sous la forme attendue par chrome.permissions. */
export function motifOrigine(backend) {
  const url = new URL(backend);
  return `${url.protocol}//${url.hostname}/*`;
}

/** Vrai si l'adresse est couverte par les permissions du manifeste (machine locale). */
export function backendLocal(backend) {
  const { hostname, protocol } = new URL(backend);
  return protocol === "http:" && (hostname === "127.0.0.1" || hostname === "localhost");
}

/** Domaines lisibles, sans doublon. Les lignes illisibles sont renvoyées à part. */
export function lireListeDomaines(texte) {
  const domaines = [], rejetes = [];
  for (const ligne of String(texte ?? "").split(/[\s,;]+/)) {
    if (!ligne) continue;
    const h = normaliserHote(ligne);
    if (h && h.includes(".")) {
      if (!domaines.includes(h)) domaines.push(h);
    } else {
      rejetes.push(ligne);
    }
  }
  return { domaines, rejetes };
}

export function nettoyer(brut) {
  const r = { ...REGLAGES_PAR_DEFAUT, ...(brut ?? {}) };
  const nom = String(r.nom ?? "").trim().slice(0, 60) || NOM_PAR_DEFAUT;
  const domaines = Array.isArray(r.domaines)
    ? lireListeDomaines(r.domaines.join("\n")).domaines
    : [...DOMAINES_PAR_DEFAUT];
  const backend = adresseBackend(r.backend) ?? BACKEND_PAR_DEFAUT;
  return { nom, domaines, backend };
}

export async function lireReglages() {
  const { reglages } = await chrome.storage.local.get("reglages");
  return nettoyer(reglages);
}

export async function ecrireReglages(reglages) {
  const propres = nettoyer(reglages);
  await chrome.storage.local.set({ reglages: propres });
  return propres;
}
