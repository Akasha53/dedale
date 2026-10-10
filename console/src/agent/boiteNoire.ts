// Boîte noire d'un agent IA : ce qu'il a lu, l'instruction cachée, ce qu'il a
// voulu faire, les actions que Dédale a retenues, les décisions et le
// résultat. Chaque étape a un titre court, une phrase en mots simples, et un
// détail qui se déplie : la donnée brute désarmée, pourquoi Dédale l'a
// repérée, ce qu'elle aurait pu provoquer, l'heure précise et les références.
//
// La console relit le journal de session, plus précis que la chaîne du
// backend. Sans journal (lecture échouée), elle se replie sur la chaîne.
// Rien n'est inventé : une étape sans preuve n'apparaît pas.

import type { Decision, Evenement, Incident, Leurre, MaillonChaine } from "../types";
import { appelInerte, decoderEntites, preuveInerte, sansPrefixe } from "./preuve";
import { fusionnerRefs, lireRef, type Ref } from "./references";
import { documentDe, sourcePour } from "./sources";
import { libelleDroit, libelleOutil, majuscule, sansCodes } from "../ui/mots";

export type CleMaillon = "source" | "consigne" | "intention" | "appel" | "decision" | "resultat" | "correctif";
// neutre : fait établi ; alerte : geste hostile ; attente : bloqué en attente
// du SOC ; protege : rien n'est sorti ; libere : l'action a été relâchée.
export type TonMaillon = "neutre" | "alerte" | "attente" | "protege" | "libere" | "absent";

export interface Brut {
  lib: string;
  valeur: string;
  mono?: boolean;
  piege?: boolean; // texte de l'instruction cachée, surligné
}

export interface DetailMaillon {
  brut: Brut[]; // ce qui s'est passé exactement
  pourquoi?: string; // pourquoi Dédale l'a repéré
  risque?: string; // ce que ça aurait pu provoquer
  refs: Ref[];
}

export interface MaillonAgent {
  cle: CleMaillon;
  id: string;
  lib: string;
  titre: string;
  texte?: string;
  horodatage?: string;
  ton: TonMaillon;
  enCours?: boolean; // décision en attente : compteur vivant
  cliquable?: boolean; // étape « Lecture » : le contenu lu s'ouvre en entier
  detail: DetailMaillon;
}

export interface AppelCible {
  outil: string;
  horodatage?: string;
  scope?: string;
  horsJeton: boolean;
  porteCanari: boolean;
  retenu: boolean;
  ev?: Evenement;
}

export type Issue = "attente" | "coupee" | "reprise" | "bloquee" | "surveillee";

export interface LectureAgent {
  maillons: MaillonAgent[];
  appel: AppelCible | null; // dernière action retenue
  appelLiberable: boolean;
  issue: Issue;
  detection?: string;
  derniereDecision?: Decision;
  enJeu: string; // ce que l'action retenue ferait, en une phrase
}

export const LIB: Record<CleMaillon, string> = {
  source: "Lecture",
  consigne: "Instruction",
  intention: "Intention",
  appel: "Action",
  decision: "Décision",
  resultat: "Résultat",
  correctif: "Correctif",
};

const NATURES_SOURCE = new Set([
  "consigne_cachee",
  "canari_mail",
  "canari_document",
  "outil_mcp_piege",
  "canari_appel",
  "injection_chatbot",
  "memoire_empoisonnee",
  "agent_usurpation",
]);

const LECTURE_PAR_GENRE: Record<string, string> = {
  mail: "Il a lu un mail venu de l'extérieur",
  document: "Il a lu un document venu de l'extérieur",
  outil: "Il a lu la description d'un outil externe",
};

const GENRE_LIB: Record<string, string> = { mail: "mail", document: "document", outil: "description d'outil" };

const DECISION_TITRE: Record<string, string> = {
  couper: "L'analyste a coupé l'agent",
  valider_riposte: "L'analyste a coupé l'agent",
  reprendre: "L'analyste a laissé passer l'action",
  ignorer: "L'analyste a classé l'alerte sans suite",
  clore: "L'analyste a clos le dossier",
};

const DECISION_RISQUE: Record<string, string> = {
  couper: "Sans coupure, l'agent aurait pu retenter l'action ou en essayer une autre.",
  valider_riposte: "Sans coupure, l'agent aurait pu retenter l'action ou en essayer une autre.",
  reprendre: "L'action est passée telle quelle, une seule fois : l'agent n'a gagné aucun droit.",
  ignorer: "L'alerte est classée : l'agent reprend son travail, toujours surveillé.",
};

// Ce qu'une action aurait provoqué si rien ne l'avait arrêtée.
const RISQUE_OUTIL: Record<string, string> = {
  lire_coffre: "L'agent aurait lu une clé secrète de l'entreprise, prête à partir.",
  envoyer_rapport: "Le rapport, et ce qu'il contient, serait parti vers une adresse extérieure.",
  envoyer_mail: "Le mail serait parti vers l'extérieur avec ce qu'il contient.",
  exporter_clients: "La base clients serait sortie de l'entreprise.",
  executer_paiement: "Un virement serait parti sans aucune validation humaine.",
  emettre_virement: "Un virement serait parti sans aucune validation humaine.",
  reconcilier_tout: "Les IBAN des clients seraient sortis dans le rapport.",
  verifier_conformite: "L'outil aurait reçu les données que la description piégée réclame.",
};

function texteClair(v: unknown): string {
  if (typeof v !== "string") return "";
  return sansPrefixe(decoderEntites(v)).texte.trim();
}

function temps(iso?: string | null): number {
  if (!iso) return Number.NaN;
  return new Date(iso).getTime();
}

function details(ev?: Evenement): Record<string, unknown> {
  return (ev?.details ?? {}) as Record<string, unknown>;
}

function court(t: string, max = 170): string {
  const s = t.replace(/\s+/g, " ").trim();
  return s.length > max ? `${s.slice(0, max).trimEnd()}…` : s;
}

function brut(lib: string, valeur: unknown, opts: Partial<Brut> = {}): Brut | null {
  const v = typeof valeur === "string" ? valeur.trim() : valeur == null ? "" : String(valeur);
  return v ? { lib, valeur: v, ...opts } : null;
}

function bruts(...liste: (Brut | null)[]): Brut[] {
  return liste.filter((b): b is Brut => b !== null);
}

const VIDE: DetailMaillon = { brut: [], refs: [] };

function issueDe(inc: Incident, derniere?: Decision, bloqueeParPasserelle = false): Issue {
  if (inc.etat === "coupee") return "coupee";
  if (derniere && (derniere.action === "reprendre" || derniere.action === "ignorer")) return "reprise";
  if (inc.etat === "suspendue") return bloqueeParPasserelle ? "bloquee" : "attente";
  return "surveillee";
}

// Range les étapes par heure. Une étape sans heure garde la place qui suit
// l'étape précédente. La chaîne du backend arrive déjà triée : c'est une
// sécurité.
function trierParHeure(maillons: MaillonAgent[]): MaillonAgent[] {
  let precedent = -Infinity;
  const cles = maillons.map((m, i) => {
    const t = temps(m.horodatage);
    if (!Number.isNaN(t)) precedent = Math.max(precedent, t);
    return { m, i, t: Number.isNaN(t) ? precedent : t };
  });
  return cles.sort((a, b) => a.t - b.t || a.i - b.i).map((c) => c.m);
}

// Références techniques d'une étape : celles que la chaîne du backend pose
// sur les événements de l'étape, celles du maillon de la passerelle
// (`details.references`, `details.boite_noire`) et celles du canary touché.
function refsDe(inc: Incident, evs: (Evenement | undefined)[], leurres: (Leurre | undefined)[] = []): Ref[] {
  const ids = new Set(evs.filter(Boolean).map((e) => e!.id));
  const listes: (Ref | null)[][] = [];
  for (const m of inc.chaine ?? []) {
    if (m.evenement_id == null || !ids.has(m.evenement_id)) continue;
    listes.push((m.risques ?? []).map((r) => lireRef(r.id)));
    listes.push(
      (m.techniques ?? []).map((t) => {
        const r = lireRef(t.id, t.cadre);
        return r ? { ...r, nom: t.nom, aConfirmer: t.a_confirmer } : null;
      })
    );
  }
  for (const e of evs) {
    const refs = details(e).references;
    if (Array.isArray(refs))
      listes.push(
        refs.map((r: { id?: string; cadre?: string; nom?: string } | string) =>
          typeof r === "string" ? lireRef(r) : r?.id ? { ...lireRef(r.id, r.cadre?.replace(/^MITRE\s+/i, ""))!, nom: r.nom } : null
        ).filter((r) => r && r.id) as Ref[]
      );
  }
  for (const l of leurres) {
    if (!l) continue;
    listes.push([...(l.risques ?? []), ...(l.techniques ?? [])].map((x) => lireRef(x)));
  }
  return fusionnerRefs(...listes);
}

// Références par étape notées par la passerelle dans `details.boite_noire`.
function refsBoiteNoire(evs: Evenement[], maillon: string, outil?: string): Ref[] {
  for (const e of [...evs].reverse()) {
    const bn = details(e).boite_noire;
    if (!Array.isArray(bn)) continue;
    const listes = bn
      .filter((m: { maillon?: string; outil?: string }) => m?.maillon === maillon && (!outil || !m.outil || m.outil === outil))
      .map((m: { references?: { id?: string; cadre?: string; nom?: string }[] }) =>
        (m.references ?? []).map((r) => (r?.id ? ({ ...lireRef(r.id, r.cadre?.replace(/^MITRE\s+/i, "")), nom: r.nom } as Ref) : null))
      );
    return fusionnerRefs(...listes).filter((r) => r && r.id);
  }
  return [];
}

function detailBoiteNoire(evs: Evenement[], maillon: string): string {
  for (const e of [...evs].reverse()) {
    const bn = details(e).boite_noire;
    if (!Array.isArray(bn)) continue;
    const m = bn.find((x: { maillon?: string; detail?: string }) => x?.maillon === maillon && typeof x.detail === "string");
    if (m) return texteClair(m.detail);
  }
  return "";
}

function resultatDe(issue: Issue, dejaPasse: boolean, horodatage: string | undefined, detail: DetailMaillon): MaillonAgent {
  const base = { cle: "resultat" as const, id: "resultat", lib: LIB.resultat, horodatage, detail };
  switch (issue) {
    case "coupee":
      return {
        ...base,
        titre: "Rien n'est sorti",
        texte: dejaPasse
          ? "L'agent est arrêté et a perdu ses accès. Seule l'action autorisée plus tôt est passée."
          : "L'agent est arrêté et a perdu ses accès.",
        ton: "protege",
      };
    case "bloquee":
      return { ...base, titre: "Rien n'est sorti", texte: "Dédale a refusé l'action et l'agent a perdu ses accès.", ton: "protege" };
    case "reprise":
      return { ...base, titre: "L'action est passée", texte: "Seule cette action est passée. L'agent reste surveillé.", ton: "libere" };
    case "attente":
      return {
        ...base,
        horodatage: undefined,
        titre: "Rien n'est sorti pour l'instant",
        texte: "L'action reste bloquée tant que vous n'avez pas choisi.",
        ton: "attente",
      };
    default:
      return { ...base, titre: "Agent actif, sous surveillance", texte: "Aucune action n'attend de décision.", ton: "neutre" };
  }
}

function decisionMaillon(d: Decision, i: number): MaillonAgent {
  return {
    cle: "decision",
    id: `decision-${i}`,
    lib: LIB.decision,
    titre: DECISION_TITRE[d.action] ?? `Décision : ${d.action}`,
    texte: `Décision prise par ${d.analyste}.`,
    horodatage: d.horodatage,
    ton: d.action === "reprendre" || d.action === "ignorer" ? "libere" : "protege",
    detail: {
      brut: bruts(brut("Choix", (DECISION_TITRE[d.action] ?? d.action).replace(/^L'analyste a /, "")), brut("Par", d.analyste)),
      pourquoi: "Dédale n'agit jamais seul : il met l'agent en pause et c'est l'analyste qui tranche.",
      risque: DECISION_RISQUE[d.action],
      refs: [],
    },
  };
}

function enJeuDe(appel: AppelCible | null): string {
  if (!appel) return "Aucune action n'attend de décision.";
  const quoi = `L'agent veut ${libelleOutil(appel.outil)}`;
  if (appel.porteCanari) return `${quoi} et y joindre un canary, vers l'extérieur.`;
  if (appel.horsJeton && appel.scope) return `${quoi}, ce que sa tâche ne prévoit pas.`;
  return `${quoi}.`;
}

// Retraits de droits faits depuis l'incident : champ `correctifs`, journal
// (type correctif) ou chaîne (phase correctif).
function correctifsDe(inc: Incident, evs: Evenement[]): MaillonAgent[] {
  const vus = new Set<string>();
  const sortie: MaillonAgent[] = [];
  const ajouter = (code: string | undefined, horodatage?: string, analyste?: string, libelle?: string) => {
    const cle = code ?? `?${sortie.length}`;
    if (vus.has(cle)) return;
    vus.add(cle);
    sortie.push({
      cle: "correctif",
      id: `correctif-${cle}`,
      lib: LIB.correctif,
      titre: "Droit retiré à l'agent",
      texte: code ? `Il ne pourra plus ${libelleDroit(code, libelle)}.` : "Un accès en trop a été retiré.",
      horodatage,
      ton: "protege",
      detail: {
        brut: bruts(brut("Droit retiré", code, { mono: true }), brut("Ce qu'il permettait", libelle), brut("Par", analyste)),
        pourquoi: "Ce droit ne sert pas à la tâche de l'agent : le garder, c'est laisser une porte ouverte.",
        risque: "Avec ce droit, un agent détourné aurait pu recommencer à la prochaine instruction cachée.",
        refs: [],
      },
    });
  };
  for (const c of inc.correctifs ?? []) ajouter(c.code, c.horodatage, c.analyste, c.libelle);
  for (const e of evs.filter((x) => x.type === "correctif")) {
    const d = details(e);
    ajouter(typeof d.droit === "string" ? d.droit : undefined, e.horodatage, typeof d.analyste === "string" ? d.analyste : undefined);
  }
  for (const m of (inc.chaine ?? []).filter((x) => x.phase === "correctif")) {
    const code = /droit\s+([a-z_]+:[a-z_]+)/i.exec(m.detail ?? "")?.[1];
    ajouter(code, m.horodatage);
  }
  return sortie;
}

// Adresse visée par un appel : un paramètre qui ressemble à une adresse mail
// ou à un lien.
function adresseVisee(parametres: unknown): string | null {
  if (!parametres || typeof parametres !== "object") return null;
  for (const v of Object.values(parametres as Record<string, unknown>)) {
    if (typeof v !== "string") continue;
    const m = /[\w.+-]+@[\w-]+(?:\.[\w-]+)+|https?:\/\/\S+/i.exec(v);
    if (m) return preuveInerte(m[0], 160);
  }
  return null;
}

function horsEntreprise(adresse: string | null): boolean {
  return Boolean(adresse) && !/orbispay(\[\.\]|\.)example/i.test(adresse!);
}

export function lireBoiteNoire(inc: Incident, leurres: Leurre[]): LectureAgent {
  const evs = [...(inc.evenements ?? [])].sort(
    (a, b) => (a.horodatage ?? "").localeCompare(b.horodatage ?? "") || a.id - b.id
  );
  const decisions = [...(inc.decisions ?? [])].sort((a, b) => (a.horodatage ?? "").localeCompare(b.horodatage ?? ""));
  const derniereDecision = decisions.length ? decisions[decisions.length - 1] : undefined;
  if (evs.length === 0) return depuisChaine(inc, decisions);

  const parId = new Map(leurres.map((l) => [l.id, l]));
  const nature = (e: Evenement) =>
    e.leurre_nature ?? (e.leurre_id ? parId.get(e.leurre_id)?.nature : undefined) ?? "";
  const maillon = (e: Evenement) => details(e).maillon;

  const entree =
    evs.find((e) => e.type === "entree_agent" && maillon(e) !== "source" && maillon(e) !== "consigne") ??
    evs.find((e) => e.type === "entree_agent");
  const appels = evs.filter((e) => e.type === "appel_outil" && maillon(e) !== "intention");
  const touches = evs.filter((e) => e.type === "leurre_touche");
  const ripostes = evs.filter((e) => e.type === "riposte");

  const evSource = evs.find((e) => maillon(e) === "source");
  const evConsigne = evs.find((e) => maillon(e) === "consigne");
  const evIntention = evs.find((e) => maillon(e) === "intention");
  const mcpEv = appels.find((e) => details(e).outil_mcp_suspect);
  const usurpationEv = appels.find((e) => details(e).provenance_invalide);
  const toucheSource =
    touches.find((e) => NATURES_SOURCE.has(nature(e))) ??
    touches.find((e) => String(details(e).type ?? "").startsWith("consigne_"));
  const docSource = documentDe(inc);
  const piege = Boolean(evSource || evConsigne || toucheSource || mcpEv || usurpationEv || docSource?.instruction_cachee);

  const ripBlocage = ripostes.find((e) => /^bloquer_/.test(String(details(e).action ?? "")));
  const ripResultat = [...ripostes].reverse().find((e) => details(e).maillon === "resultat" || details(e).action === "couper");

  const demandeTache = texteClair(details(entree).texte);
  const tache = texteClair(
    (details(entree).droits as Record<string, unknown> | undefined)?.tache ?? details(entree).tache
  );

  // Actions retenues (mode protégé) ou refusées hors droits. À défaut, l'appel
  // qui a suivi l'instruction cachée.
  const lireAppel = (e: Evenement): AppelCible => {
    const d = details(e);
    const violation = d.violation_droits as Record<string, unknown> | undefined;
    const exfil = d.exfiltration as Record<string, unknown> | undefined;
    return {
      outil: e.outil ?? String(violation?.outil ?? "agir"),
      horodatage: e.horodatage,
      scope: String(violation?.scope_requis ?? d.scope_requis ?? "") || undefined,
      horsJeton: Boolean(violation) || d.motif === "droits",
      porteCanari: d.motif === "canari" || Boolean(exfil && Array.isArray(exfil.canaris) && exfil.canaris.length),
      retenu: Boolean(d.retenu),
      ev: e,
    };
  };
  let cibles = appels.filter((e) => details(e).retenu || details(e).violation_droits).map(lireAppel);
  if (cibles.length === 0) {
    const tDet = temps(touches[0]?.horodatage);
    const outilTouche = touches.find((e) => e.outil)?.outil;
    const avant = (e: Evenement) => Number.isNaN(tDet) || temps(e.horodatage) <= tDet;
    const ev =
      (outilTouche ? [...appels].reverse().find((e) => e.outil === outilTouche && avant(e)) : undefined) ??
      (piege ? [...appels].reverse().find(avant) : undefined);
    if (ev) cibles = [{ ...lireAppel(ev), porteCanari: Boolean(outilTouche) }];
  }
  const appel = cibles.length ? cibles[cibles.length - 1] : null;

  const detection =
    evConsigne?.horodatage ?? touches[0]?.horodatage ?? cibles[0]?.horodatage ?? inc.temps_session?.detecte_a ?? undefined;

  const issue = issueDe(inc, derniereDecision, Boolean(ripBlocage));
  const statutFerme = inc.statut === "clos" || inc.statut === "ignore";
  const appelLiberable =
    issue === "attente" && !statutFerme && appel !== null && (appel.retenu || !appel.horsJeton) && !usurpationEv;

  const maillons: MaillonAgent[] = [];

  // 1. Lecture : le contenu piégé, sinon la tâche confiée.
  if (piege) {
    const genre = sourcePour(inc).genre;
    const leurreSource = toucheSource?.leurre_id ? parId.get(toucheSource.leurre_id) : undefined;
    const doc =
      texteClair(docSource?.titre) ||
      texteClair((details(evSource).source as Record<string, unknown> | undefined)?.document) ||
      texteClair(leurreSource?.emplacement) ||
      (mcpEv?.outil ?? "");
    const externe =
      docSource?.origine === "externe" ||
      (details(evSource).source as Record<string, unknown> | undefined)?.origine === "externe" ||
      Boolean(mcpEv);
    maillons.push({
      cle: "source",
      id: "source",
      lib: LIB.source,
      titre: LECTURE_PAR_GENRE[genre] ?? "Il a lu un contenu venu de l'extérieur",
      texte: doc ? `« ${sansCodes(doc)} »` : undefined,
      horodatage: evSource?.horodatage ?? mcpEv?.horodatage ?? toucheSource?.horodatage,
      ton: "neutre",
      cliquable: true,
      detail: {
        brut: bruts(
          brut("Contenu", doc ? sansCodes(doc) : ""),
          brut("Type", GENRE_LIB[genre]),
          brut("De", docSource?.expediteur ? preuveInerte(decoderEntites(docSource.expediteur), 120) : ""),
          brut("Origine", externe ? "extérieur à Orbis Pay" : ""),
          brut("Lu avec l'outil", evSource?.outil ?? mcpEv?.outil, { mono: true }),
          brut("Empreinte", docSource?.empreinte ?? (details(evSource).source as Record<string, unknown> | undefined)?.empreinte, { mono: true })
        ),
        pourquoi: externe
          ? "Ce contenu vient de l'extérieur : Dédale le traite comme non fiable et regarde ce que l'agent en fait."
          : "Dédale garde la trace de tout ce que l'agent lit.",
        risque: "Un contenu venu de l'extérieur peut donner des ordres à l'agent sans que personne ne le voie.",
        refs: fusionnerRefs(refsDe(inc, [evSource, mcpEv]), refsBoiteNoire(evs, "source")),
      },
    });
  } else if (entree) {
    const jeton = (details(entree).droits as Record<string, unknown> | undefined)?.jeton;
    maillons.push({
      cle: "source",
      id: "source",
      lib: LIB.source,
      titre: "Il travaillait sur sa tâche",
      texte: demandeTache ? `« ${court(demandeTache, 140)} »` : tache ? `Tâche : ${tache.replace(/_/g, " ")}.` : undefined,
      horodatage: entree.horodatage,
      ton: "neutre",
      detail: {
        brut: bruts(
          brut("Demande", demandeTache),
          brut("Tâche", tache, { mono: true }),
          brut("Droits prévus", Array.isArray(jeton) ? jeton.map((c) => libelleDroit(String(c))).join(", ") : "")
        ),
        pourquoi: "Point de départ : ce que l'agent devait faire. Tout ce qui suit est comparé à cette tâche.",
        refs: [],
      },
    });
  }

  // 2. Instruction cachée.
  if (piege) {
    // Le maillon de la passerelle garde le constat entier ; l'extrait de
    // l'événement peut être raccourci.
    const extrait = (detailBoiteNoire(evs, "consigne") || texteClair(details(evConsigne).extrait)).replace(/\s*\[(…|\.\.\.)\]\s*\.?$/, "");
    const demande = /Elle demande de ([\s\S]+?)\.?$/i.exec(extrait)?.[1];
    const leurre = toucheSource?.leurre_id ? parId.get(toucheSource.leurre_id) : undefined;
    const descr = texteClair(leurre?.description);
    const textePiege =
      docSource?.segments?.filter((s) => s.piege).map((s) => decoderEntites(s.texte)).join(" ") ||
      (docSource?.texte_piege ? decoderEntites(docSource.texte_piege) : "");
    const canary =
      (typeof details(evConsigne).canari_id === "string" ? (details(evConsigne).canari_id as string) : "") ||
      evConsigne?.leurre_id ||
      toucheSource?.leurre_id ||
      docSource?.canari_id ||
      "";
    maillons.push({
      cle: "consigne",
      id: "consigne",
      lib: LIB.consigne,
      titre: mcpEv
        ? "La description de l'outil cachait une instruction"
        : usurpationEv
          ? "Un faux collègue lui a donné un ordre"
          : "Une instruction cachée, invisible pour un humain",
      texte: demande
        ? `Elle lui demande de ${court(sansCodes(demande))}.`
        : descr
          ? court(sansCodes(descr))
          : "Le contenu s'adressait à l'agent, pas à la personne qui l'a reçu.",
      horodatage: evConsigne?.horodatage ?? toucheSource?.horodatage ?? mcpEv?.horodatage,
      ton: "alerte",
      detail: {
        brut: bruts(
          brut("Texte caché", textePiege ? preuveInerte(textePiege, 900) : "", { piege: true }),
          brut("Constat de Dédale", textePiege ? "" : preuveInerte(extrait || descr, 400)),
          brut("Canary touché", canary, { mono: true })
        ),
        pourquoi: mcpEv
          ? "La description de l'outil donne des ordres à l'agent : un outil honnête ne fait pas ça."
          : canary
            ? "Un canary a été touché : ce texte ne s'adresse pas à une personne, seul un agent IA le lit et le suit."
            : "Le contenu donne des ordres à l'agent, hors de sa tâche.",
        risque: demande
          ? `Si l'agent l'avait suivie jusqu'au bout, il aurait pu ${court(sansCodes(demande), 200)}.`
          : "Si rien ne l'avait arrêté, l'agent aurait exécuté cet ordre avec ses propres accès.",
        refs: fusionnerRefs(refsDe(inc, [evConsigne, toucheSource], [leurre]), refsBoiteNoire(evs, "consigne")),
      },
    });
  }

  // 3. Intention : le but que l'agent annonce, ou sa sortie de tâche.
  const objectif = texteClair(details(evIntention).objectif);
  const pourquoiTache = demandeTache
    ? `Ce but ne correspond pas à sa tâche : « ${court(demandeTache, 120)} ».`
    : "Ce but ne correspond pas à la tâche confiée à l'agent.";
  const risqueIntention = piege
    ? "L'agent travaille désormais pour l'auteur de l'instruction cachée, avec les accès d'Orbis Pay."
    : "L'agent agit hors du cadre prévu, avec des accès qu'on ne lui a pas donnés pour ça.";
  if (objectif) {
    maillons.push({
      cle: "intention",
      id: "intention",
      lib: LIB.intention,
      titre: piege ? "Il change de but" : "Il sort de sa tâche",
      texte: `Il annonce : « ${court(sansCodes(objectif), 150)} »`,
      horodatage: evIntention?.horodatage,
      ton: "alerte",
      detail: {
        brut: bruts(brut("Ce que l'agent annonce", preuveInerte(objectif, 600)), brut("Outil visé", evIntention?.outil, { mono: true })),
        pourquoi: pourquoiTache,
        risque: risqueIntention,
        refs: fusionnerRefs(refsDe(inc, [evIntention]), refsBoiteNoire(evs, "intention", evIntention?.outil ?? undefined)),
      },
    });
  } else if (piege && toucheSource) {
    maillons.push({
      cle: "intention",
      id: "intention",
      lib: LIB.intention,
      titre: "Il change de but",
      texte: "Il laisse sa tâche de côté pour suivre l'instruction cachée.",
      horodatage: toucheSource.horodatage,
      ton: "alerte",
      detail: { brut: [], pourquoi: pourquoiTache, risque: risqueIntention, refs: [] },
    });
  } else if (appel?.horsJeton) {
    maillons.push({
      cle: "intention",
      id: "intention",
      lib: LIB.intention,
      titre: "Il sort de sa tâche",
      texte: `Il veut ${libelleOutil(appel.outil)}, ce que sa tâche ne demande pas.`,
      horodatage: appel.horodatage,
      ton: "alerte",
      detail: { brut: [], pourquoi: pourquoiTache, risque: risqueIntention, refs: [] },
    });
  }

  // 4. Actions retenues, chacune suivie de la décision qui l'a tranchée.
  cibles.forEach((c, i) => {
    const t = temps(c.horodatage);
    const tranchee = decisions.find((d) => !Number.isNaN(t) && temps(d.horodatage) >= t);
    const ton: TonMaillon = tranchee
      ? tranchee.action === "reprendre" || tranchee.action === "ignorer"
        ? "libere"
        : "protege"
      : ripBlocage
        ? "protege"
        : issue === "attente"
          ? "attente"
          : "protege";
    const d = details(c.ev);
    const adresse = adresseVisee(d.parametres);
    const exfil = d.exfiltration as Record<string, unknown> | undefined;
    const canaris = Array.isArray(exfil?.canaris) ? (exfil!.canaris as string[]).join(", ") : "";
    const pourquoi = [
      c.horsJeton && c.scope ? `L'outil n'est pas dans les droits de sa tâche : il exige « ${libelleDroit(c.scope)} ».` : "",
      c.porteCanari ? "Un canary se trouve dans ce que l'agent voulait envoyer." : "",
      horsEntreprise(adresse) ? "L'adresse visée est hors de l'entreprise." : "",
    ]
      .filter(Boolean)
      .join(" ");
    const suite = ripBlocage && !tranchee ? "Dédale l'a refusée." : "Dédale l'a retenue avant qu'elle parte.";
    const touchesLiees = touches.filter((e) => e.outil === c.outil && temps(e.horodatage) >= t);
    maillons.push({
      cle: "appel",
      id: `appel-${i}`,
      lib: LIB.appel,
      titre: majuscule(libelleOutil(c.outil)),
      texte: [
        c.porteCanari
          ? "Elle emporte un canary vers l'extérieur."
          : c.horsJeton && c.scope
            ? `Sa tâche ne prévoit pas l'accès « ${libelleDroit(c.scope)} ».`
            : "",
        suite,
      ]
        .filter(Boolean)
        .join(" "),
      horodatage: c.horodatage,
      ton,
      detail: {
        brut: bruts(
          brut("Outil appelé", c.outil, { mono: true }),
          brut("Paramètres", d.parametres ? appelInerte(c.outil, d.parametres, 600) : "", { mono: true }),
          brut("Droit exigé", c.scope, { mono: true }),
          brut("Adresse visée", adresse ?? "", { mono: true }),
          brut("Canary emporté", canaris, { mono: true })
        ),
        pourquoi: pourquoi || "L'action suit l'instruction cachée : Dédale la retient avant qu'elle s'exécute.",
        risque: RISQUE_OUTIL[c.outil] ?? "L'action aurait été exécutée avec les accès de l'agent, sans contrôle.",
        refs: fusionnerRefs(refsDe(inc, [c.ev, ...touchesLiees]), refsBoiteNoire(evs, "appel_outil", c.outil)),
      },
    });
  });

  // 5. Décisions, ou l'attente.
  decisions.forEach((d, i) => maillons.push(decisionMaillon(d, i)));
  if (decisions.length === 0) {
    maillons.push({
      cle: "decision",
      id: "decision-attente",
      lib: LIB.decision,
      titre: statutFerme ? "Dossier fermé sans décision notée" : "En attente de votre décision",
      texte: statutFerme ? undefined : "Dédale a mis l'agent en pause. Il attend votre choix.",
      // Après la dernière action retenue : c'est elle qui attend.
      horodatage: appel?.horodatage ?? detection,
      ton: statutFerme ? "neutre" : "attente",
      enCours: !statutFerme && (issue === "attente" || issue === "bloquee"),
      detail: {
        brut: [],
        pourquoi: "Dédale n'agit jamais seul : il met l'agent en pause et c'est l'analyste qui tranche.",
        risque: statutFerme ? undefined : "Tant que personne ne décide, rien ne part.",
        refs: [],
      },
    });
  }

  // 6. Correctifs, puis résultat.
  maillons.push(...correctifsDe(inc, evs));
  const dejaPasse = decisions.some((d) => d.action === "reprendre") && issue === "coupee";
  const dRes = details(ripResultat);
  maillons.push(
    resultatDe(issue, dejaPasse, ripResultat?.horodatage ?? inc.temps_session?.confine_a ?? derniereDecision?.horodatage ?? undefined, {
      brut: bruts(
        brut("Compte rendu de la passerelle", preuveInerte(texteClair(dRes.resultat) || texteClair(dRes.raison), 400)),
        brut("Accès retirés", dRes.jeton_revoque === true ? "oui" : "")
      ),
      pourquoi: ripResultat ? "Confirmé par la passerelle de Dédale, qui contrôle chaque action de l'agent." : undefined,
      refs: [],
    })
  );

  return {
    maillons: trierParHeure(maillons),
    appel,
    appelLiberable,
    issue,
    detection,
    derniereDecision,
    enJeu: enJeuDe(appel),
  };
}

const PHASE_CLE: Record<string, CleMaillon> = {
  entree: "source",
  consigne: "consigne",
  outil: "appel",
  sortie: "appel",
  riposte: "decision",
  correctif: "correctif",
};

// Repli sans journal : la chaîne du backend, une étape par maillon, texte
// nettoyé des codes.
function depuisChaine(inc: Incident, decisions: Decision[]): LectureAgent {
  const derniere = decisions[decisions.length - 1];
  const issue = issueDe(inc, derniere);
  const statutFerme = inc.statut === "clos" || inc.statut === "ignore";
  const chaine = [...(inc.chaine ?? [])].filter((m) => m.phase !== "riposte" && m.phase !== "correctif");
  const outil = [...chaine].reverse().find((m) => m.phase === "outil" || m.phase === "sortie");
  const versMaillon = (m: MaillonChaine, i: number): MaillonAgent => {
    const cle = PHASE_CLE[m.phase] ?? "intention";
    return {
      cle,
      id: `chaine-${m.ordre}-${i}`,
      lib: LIB[cle],
      titre: sansCodes(preuveInerte(m.titre, 120)),
      texte: sansCodes(preuveInerte(m.detail, 220)) || undefined,
      horodatage: m.horodatage,
      ton: cle === "source" ? "neutre" : cle === "appel" ? (issue === "attente" ? "attente" : "protege") : "alerte",
      cliquable: cle === "source" && Boolean(m.document_source || m.canari_id || m.leurre_id),
      detail: {
        brut: bruts(brut("Constat", preuveInerte(m.detail, 600)), brut("Canary", m.canari_id, { mono: true })),
        refs: fusionnerRefs(
          (m.risques ?? []).map((r) => lireRef(r.id)),
          (m.techniques ?? []).map((t) => {
            const r = lireRef(t.id, t.cadre);
            return r ? { ...r, nom: t.nom, aConfirmer: t.a_confirmer } : null;
          })
        ),
      },
    };
  };
  const maillons: MaillonAgent[] = chaine.map(versMaillon);
  decisions.forEach((d, i) => maillons.push(decisionMaillon(d, i)));
  if (decisions.length === 0) {
    maillons.push({
      cle: "decision",
      id: "decision-attente",
      lib: LIB.decision,
      titre: statutFerme ? "Dossier fermé" : "En attente de votre décision",
      texte: statutFerme ? undefined : "Dédale a mis l'agent en pause. Il attend votre choix.",
      horodatage: chaine.find((m) => m.phase === "consigne")?.horodatage ?? outil?.horodatage,
      ton: statutFerme ? "neutre" : "attente",
      enCours: !statutFerme && issue === "attente",
      detail: VIDE,
    });
  }
  maillons.push(...correctifsDe(inc, []));
  maillons.push(resultatDe(issue, false, issue === "coupee" || issue === "reprise" ? derniere?.horodatage : undefined, VIDE));
  const appel: AppelCible | null = outil
    ? { outil: "agir", horodatage: outil.horodatage, horsJeton: false, porteCanari: false, retenu: true }
    : null;
  return {
    maillons: trierParHeure(maillons),
    appel,
    appelLiberable: issue === "attente" && !statutFerme && Boolean(outil),
    issue,
    detection: chaine.find((m) => m.phase === "consigne")?.horodatage ?? outil?.horodatage,
    derniereDecision: derniere,
    enJeu: outil ? `L'agent veut ${sansCodes(preuveInerte(outil.titre, 120)).toLowerCase()}.` : enJeuDe(null),
  };
}
