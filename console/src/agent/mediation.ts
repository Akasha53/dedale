// « Ce qui s'est passé » pour les trois incidents de la médiation de la
// passerelle (avenant « médiation universelle » de CONTRATS.md) : outil
// inconnu (C-8A61), canal détourné (C-5B27), outil modifié (C-3F90).
//
// La passerelle range le constat sous le nom du motif dans l'événement
// `appel_outil` retenu : outil, serveur MCP, règle, canaris, secrets,
// destinations, encodages. On en tire trois phrases : ce que l'agent a fait,
// ce que portait l'appel, et ce qui l'a retenu. Les canaris sont nommés par
// leur identifiant, jamais par leur valeur ; les destinations passent ensuite
// par desarmer() comme toute phrase de la synthèse.

import type { Incident } from "../types";
import type { EtatVue } from "./IncidentAgent";

export const TYPES_MEDIATION = ["interne_outil_inconnu", "interne_canal_detourne", "interne_outil_modifie"] as const;

type Motif = "outil_inconnu" | "canal_detourne" | "outil_modifie";

const MOTIF_DU_TYPE: Record<string, Motif> = {
  interne_outil_inconnu: "outil_inconnu",
  interne_canal_detourne: "canal_detourne",
  interne_outil_modifie: "outil_modifie",
};

const REGLE_PAR_DEFAUT: Record<Motif, string> = {
  outil_inconnu: "C-8A61",
  canal_detourne: "C-5B27",
  outil_modifie: "C-3F90",
};

interface Constat {
  outil?: string;
  serveur_mcp?: string | null;
  regle?: string;
  libelle?: string;
  canaris?: string[];
  secrets?: string[];
  destinations?: string[];
  encodages?: string[];
  inspection_incomplete?: string | null;
  empreinte_avant?: string;
  empreinte_apres?: string;
}

function liste(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string" && x.length > 0) : [];
}

// Le dernier constat de ce motif dans la session de l'incident.
function lireConstat(incident: Incident, motif: Motif): Constat | null {
  const evs = incident.evenements ?? [];
  for (let i = evs.length - 1; i >= 0; i--) {
    const brut = evs[i].details?.[motif];
    if (brut && typeof brut === "object") return brut as Constat;
  }
  return null;
}

function enumerer(mots: string[]): string {
  if (mots.length <= 1) return mots.join("");
  return `${mots.slice(0, -1).join(", ")} et ${mots[mots.length - 1]}`;
}

function court(empreinte?: string): string {
  return (empreinte ?? "").replace(/^sha256:/, "").slice(0, 8);
}

// Ce que portaient les paramètres : canaris (identifiant seul), secrets,
// destinations, encodages, ou ce qui ne se relisait pas.
function contenu(c: Constat): string | null {
  const morceaux: string[] = [];
  const canaris = liste(c.canaris).filter((x) => !Object.values(REGLE_PAR_DEFAUT).includes(x));
  if (canaris.length)
    morceaux.push(
      canaris.length > 1
        ? `les canary ${enumerer(canaris)} (des faux secrets posés par sAIfe, valeurs masquées)`
        : `le canary ${canaris[0]} (un faux secret posé par sAIfe, valeur masquée)`
    );
  const secrets = liste(c.secrets);
  if (secrets.length) morceaux.push(secrets.length > 1 ? `${secrets.length} secrets (masqués)` : "un secret (masqué)");
  const dest = liste(c.destinations);
  if (dest.length) morceaux.push(`${dest.length > 1 ? "les adresses extérieures" : "l'adresse extérieure"} ${enumerer(dest)}`);
  if (morceaux.length === 0 && !c.inspection_incomplete) return null;
  const phrases: string[] = [];
  if (morceaux.length) phrases.push(`L'appel portait ${enumerer(morceaux)}.`);
  const enc = liste(c.encodages);
  if (enc.length) phrases.push(`Une partie était cachée sous un encodage : ${enumerer(enc)}.`);
  if (c.inspection_incomplete) phrases.push(`Un paramètre ne se relisait pas en entier (${c.inspection_incomplete}).`);
  return phrases.join(" ");
}

function issue(vue: EtatVue): string {
  switch (vue) {
    case "attente":
      return "rien ne s'exécute avant votre décision.";
    case "coupee":
      return "l'analyste a coupé l'agent, l'appel n'a jamais tourné.";
    case "refusee":
      return "l'appel a été refusé, rien n'est parti.";
    case "reprise":
      return "l'analyste a laissé passer cet appel une fois ; le suivant sera retenu de nouveau.";
    case "classee":
      return "le dossier est classé sans suite.";
    default:
      return "le dossier est clos.";
  }
}

export function phrasesMediation(incident: Incident, vue: EtatVue): string[] | null {
  const motif = incident.type ? MOTIF_DU_TYPE[incident.type] : undefined;
  if (!motif) return null;
  const c = lireConstat(incident, motif);
  if (!c?.outil) return null;
  const outil = `« ${c.outil} »`;
  const serveur = c.serveur_mcp ? `du serveur MCP ${c.serveur_mcp}` : null;
  const regle = c.regle || REGLE_PAR_DEFAUT[motif];

  let premiere: string;
  if (motif === "outil_inconnu") {
    premiere = `L'agent a appelé ${outil}${serveur ? `, un outil ${serveur},` : ""} qui n'est pas dans sa boîte à outils.`;
  } else if (motif === "canal_detourne") {
    premiere = `L'agent s'est servi de ${outil}${c.serveur_mcp ? ` (serveur MCP ${c.serveur_mcp})` : ""}, un outil qui n'envoie rien, pour faire sortir des données.`;
  } else {
    const avant = court(c.empreinte_avant);
    const apres = court(c.empreinte_apres);
    premiere = `La description de ${outil}${serveur ? `, outil ${serveur},` : ""} a changé pendant la session, après un premier appel${
      avant && apres ? ` (empreinte ${avant} puis ${apres})` : ""
    }.`;
  }

  return [premiere, contenu(c), `La règle ${regle} de la passerelle a retenu l'appel : ${issue(vue)}`].filter(
    (p): p is string => Boolean(p)
  );
}

// Résumés de repli du contrat, quand l'événement n'est pas encore arrivé.
export const REPLI_MEDIATION: Record<string, string> = {
  interne_outil_inconnu:
    "L'agent a appelé un outil qui n'est pas dans sa boîte à outils. sAIfe retient tout outil qu'il ne connaît pas avant qu'il s'exécute.",
  interne_canal_detourne:
    "L'agent a glissé une donnée sensible ou une adresse extérieure dans un outil qui ne sert pas à envoyer. sAIfe l'a retenu avant qu'il s'exécute.",
  interne_outil_modifie:
    "Un outil déjà utilisé a changé de description pendant la session. sAIfe retient son prochain appel jusqu'à votre décision.",
};
