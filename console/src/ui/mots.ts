// Mots simples pour tout ce que la console affiche. Le backend parle en codes
// (droits « coffre:lire », outils « lire_coffre », états « suspendue ») ; ici
// on les traduit pour quelqu'un qui n'est pas du métier. Une valeur inconnue
// retombe sur une forme lisible, jamais sur une erreur.

import type { Activite, Incident, TypeIncident } from "../types";

// Ce que permet un droit, à l'infinitif : « L'agent ne pourra plus … ».
const DROITS: Record<string, string> = {
  "mail:lire": "lire les mails",
  "mail:envoyer": "envoyer des mails",
  "coffre:lire": "ouvrir le coffre des clés secrètes",
  "paiement:executer": "faire des virements",
  "virements:emettre": "faire des virements",
  "contact:exporter": "exporter les contacts clients",
  "clients:export": "exporter la base clients",
  "clients:lire": "lire la base clients",
  "factures:lire": "lire les factures",
  "document:lire": "lire les documents internes",
  "outil:mcp": "utiliser des outils externes",
  "appel:lire": "lire les transcriptions d'appels",
  "memoire:lire": "lire sa mémoire",
  "memoire:ecrire": "écrire dans sa mémoire",
  "resume:local": "faire des résumés",
  "rapport:envoyer": "envoyer des rapports",
};

export function libelleDroit(code?: string | null, libelle?: string | null): string {
  if (!code) return libelle ? minuscule(libelle) : "cet accès";
  return DROITS[code] ?? (libelle ? minuscule(libelle) : code.replace(/[:_]/g, " "));
}

// Ce que fait un outil, à l'infinitif : « L'agent veut … ».
const OUTILS: Record<string, string> = {
  lire_mail: "lire un mail",
  envoyer_mail: "envoyer un mail",
  resumer: "faire un résumé",
  envoyer_rapport: "envoyer un rapport",
  lire_coffre: "ouvrir le coffre des clés secrètes",
  executer_paiement: "faire un virement",
  emettre_virement: "faire un virement",
  chercher_document: "ouvrir un document",
  verifier_conformite: "utiliser un outil externe de « conformité »",
  convertir_montant: "convertir un montant",
  exporter_clients: "exporter la base clients",
  reconcilier_tout: "utiliser un faux outil « tout rapprocher »",
  lire_factures: "lire les factures",
  rapprocher_factures: "rapprocher des factures",
  chercher_appel: "lire une transcription d'appel",
  lire_memoire: "lire sa mémoire",
  ecrire_memoire: "écrire dans sa mémoire",
  "réponse finale": "rédiger sa réponse",
};

export function libelleOutil(outil?: string | null): string {
  if (!outil) return "agir";
  return OUTILS[outil] ?? outil.replace(/_/g, " ");
}

// Nom d'agent lisible : « orbis-assistant » devient « Assistant Orbis ».
const AGENTS: Record<string, string> = {
  "orbis-assistant": "Assistant Orbis",
  "assistant-rh": "Assistant RH",
};

export function nomAgent(id?: string | null): string {
  if (!id) return "Agent IA";
  if (AGENTS[id]) return AGENTS[id];
  return majuscule(id.replace(/[-_]+/g, " "));
}

// Verdict d'une action dans le fil des agents.
export const VERDICT: Record<string, { lib: string; cls: string }> = {
  autorise: { lib: "Autorisée", cls: "ok" },
  retenu: { lib: "Retenue", cls: "attente" },
  refuse: { lib: "Refusée", cls: "refus" },
};

// Raison d'un verdict, en clair. La raison brute du backend reste en infobulle.
export function raisonActivite(a: Activite, enAttente = true): string {
  const r = decoder(a.raison ?? "");
  const droit = a.droit ? `« ${libelleDroit(a.droit)} »` : "";
  if (a.verdict === "autorise") {
    if (/libéré/i.test(r)) return "vous l'avez laissée passer";
    if (/MCP|suspecte/i.test(r)) return "outil externe douteux, action notée";
    return "prévue pour sa tâche";
  }
  if (a.verdict === "retenu") {
    const suite = enAttente ? ", attend votre décision" : "";
    if (/canar[iy]/i.test(r)) return `elle emporte un canary${suite}`;
    if (droit) return `accès ${droit} non prévu${suite}`;
    return enAttente ? "attend votre décision" : "retenue par Dédale";
  }
  if (/coup/i.test(r)) return "annulée : l'agent a été arrêté";
  if (/retir/i.test(r)) return "ce droit lui a été retiré";
  if (/délai|aucune décision/i.test(r)) return "personne n'a répondu à temps";
  if (droit) return `accès ${droit} non prévu pour sa tâche`;
  return "bloquée par Dédale";
}

// Titre court d'un incident, sans code ni identifiant.
const TITRES: Record<string, string> = {
  interne_canari: "Agent IA détourné par une instruction cachée",
  interne_outil_mcp: "Agent IA piégé par un faux outil",
  interne_droits: "Agent IA sorti de sa tâche",
  interne_appel: "Agent IA détourné par un appel piégé",
  interne_chatbot: "Assistant détourné par un message piégé",
  interne_inter_agent: "Agent IA trompé par un faux collègue",
  interne_memoire: "Agent IA trompé par une fausse mémoire",
  humain_secret: "Clé secrète sur le point de sortir",
  humain_mail_externe: "Données envoyées à une adresse extérieure",
  humain_upload_ia: "Fichier interne déposé sur une IA non autorisée",
  humain_phishing: "Clic sur un lien piégé",
};

export function titreIncident(inc: Pick<Incident, "type" | "titre">): string {
  const base = TITRES[inc.type ?? ""];
  if (!base) return sansCodes(inc.titre || "Incident");
  if (inc.type === "interne_canari") {
    if (/mail/i.test(inc.titre)) return "Agent IA détourné par un mail piégé";
    if (/document|relev/i.test(inc.titre)) return "Agent IA détourné par un document piégé";
  }
  return base;
}

// Ce qui s'est passé pour un salarié, en une phrase.
const GESTES: Record<string, string> = {
  humain_secret: "Un salarié allait coller une clé secrète sur un site extérieur",
  humain_mail_externe: "Un salarié a voulu envoyer des données de l'entreprise à une adresse extérieure",
  humain_upload_ia: "Un salarié a voulu déposer un fichier interne sur une IA non autorisée",
  humain_phishing: "Un salarié a cliqué sur un lien piégé dans un faux mail",
};

export function phraseSalarie(type?: TypeIncident, choix?: "continuer" | "annuler"): string {
  const geste = GESTES[type ?? ""] ?? "Un salarié a fait un geste risqué";
  if (choix === "annuler") return `${geste}. Dédale l'a prévenu et il a annulé.`;
  if (choix === "continuer") return `${geste}. Dédale l'a prévenu, il a continué quand même.`;
  return `${geste}. Dédale l'a prévenu au moment du geste.`;
}

// Refus d'office : la passerelle a refusé l'action elle-même (droit absent du
// jeton de tâche, faux collègue), sans attendre personne. Le détail porte le
// journal (riposte « bloquer_… ») ; la liste n'a que la chaîne : un maillon
// riposte qui suit l'action de moins d'une seconde et demie, sans décision
// humaine avant lui. Une riposte après décision, ou au bout du délai
// d'attente, ne compte pas.
export function refusDOffice(inc: Incident): boolean {
  if (inc.source !== "interne" && !(inc.type ?? "").startsWith("interne_")) return false;
  if (inc.evenements?.length) {
    return inc.evenements.some(
      (e) => e.type === "riposte" && /^bloquer_/.test(String((e.details as Record<string, unknown> | undefined)?.action ?? ""))
    );
  }
  const t = (iso?: string | null) => (iso ? new Date(iso).getTime() : Number.NaN);
  const decisions = (inc.decisions ?? []).map((d) => t(d.horodatage));
  const chaine = inc.chaine ?? [];
  return chaine.some((m, k) => {
    if (m.phase !== "riposte") return false;
    const tr = t(m.horodatage);
    const action = [...chaine.slice(0, k)].reverse().find((x) => x.phase === "outil" || x.phase === "sortie");
    const ta = t(action?.horodatage);
    if (Number.isNaN(tr) || Number.isNaN(ta) || tr < ta || tr - ta > 1500) return false;
    return !decisions.some((d) => d <= tr);
  });
}

// État d'un incident, pour la liste et l'en-tête. `cls` porte la couleur :
// attente (orange) seulement quand un appel attend une décision humaine.
// `aTraiter` garde la ligne dans la liste : un refus d'office reste à clore.
export function etatIncident(inc: Incident): { lib: string; cls: string; aTraiter: boolean } {
  const humain = inc.source === "humain" || (inc.type ?? "").startsWith("humain_");
  if (inc.statut === "ignore") return { lib: "Classé sans suite", cls: "neutre", aTraiter: false };
  if (humain) {
    if (inc.statut === "clos") return { lib: "Clos", cls: "neutre", aTraiter: false };
    return { lib: "À traiter", cls: "attente", aTraiter: true };
  }
  if (inc.etat === "coupee") return { lib: "Agent arrêté", cls: "ok", aTraiter: false };
  if (inc.statut === "clos") return { lib: "Clos", cls: "neutre", aTraiter: false };
  if (inc.etat === "suspendue" && refusDOffice(inc)) {
    // Retirer le droit en cause règle aussi le dossier, comme pour les autres.
    if ((inc.correctifs?.length ?? 0) > 0) return { lib: "Droit retiré", cls: "ok", aTraiter: false };
    return { lib: "Refusé, à clore", cls: "ok", aTraiter: true };
  }
  if (inc.etat === "suspendue") return { lib: "À décider", cls: "attente", aTraiter: true };
  if (inc.statut === "surveille" || inc.etat === "active") return { lib: "Repris, surveillé", cls: "libere", aTraiter: false };
  if ((inc.correctifs?.length ?? 0) > 0) return { lib: "Droit retiré", cls: "ok", aTraiter: false };
  return { lib: "Traité", cls: "ok", aTraiter: false };
}

// Un incident reste dans la liste tant qu'il demande un geste de l'analyste :
// une décision, ou la clôture d'un refus d'office.
export function estATraiter(inc: Incident): boolean {
  return etatIncident(inc).aTraiter;
}

// Un appel est suspendu et attend un humain : seul cas « à décider » (orange).
export function attendDecision(inc: Incident): boolean {
  return etatIncident(inc).cls === "attente";
}

export const GRAVITE: Record<string, string> = {
  faible: "Faible",
  moyenne: "Moyenne",
  haute: "Haute",
  critique: "Critique",
};

export const ACTION_CONSEILLEE: Record<string, string> = {
  couper: "Couper l'agent",
  valider_riposte: "Couper l'agent",
  reprendre: "Laisser passer l'action",
  ignorer: "Classer sans suite",
  clore: "Clore le dossier",
};

// Retire les codes techniques d'un texte : « (canari C-0021) », « (C-0033) »,
// identifiants de session entre parenthèses.
export function sansCodes(t: string): string {
  return t
    .replace(/\s*\((?:canari|leurre)?\s*[CL]-[A-Z0-9-]+\)/gi, "")
    .replace(/\s*\((?:poste|sess|session|badge|banc|jury)[^)]*\)/gi, "")
    .trim();
}

export function decoder(t: string): string {
  return t
    .replace(/&#x27;|&#39;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&");
}

export function majuscule(t: string): string {
  return t ? t.charAt(0).toUpperCase() + t.slice(1) : t;
}

export function minuscule(t: string): string {
  return t ? t.charAt(0).toLowerCase() + t.slice(1) : t;
}
