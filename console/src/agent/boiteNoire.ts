// Boîte noire d'un agent IA, lue comme une chaîne de six maillons :
// source → consigne → intention → appel d'outil → décision → résultat.
//
// Le backend reconstruit sa propre chaîne (phases entree|consigne|outil|sortie|
// riposte). La console la relit à partir du journal de session, plus précis :
// canari touché, appel d'outil et ses paramètres, riposte de la passerelle,
// décision de l'analyste. Sans journal (mock, lecture échouée), elle se replie
// sur la chaîne du backend. Rien n'est inventé : un maillon sans preuve le dit.

import type { Decision, Evenement, Incident, Leurre, MaillonChaine } from "../types";
import { appelInerte, decoderEntites, domaineExterne, preuveInerte, sansPrefixe } from "./preuve";
import { fusionnerRefs, lireRef, type Ref } from "./references";

export type CleMaillon = "source" | "consigne" | "intention" | "appel" | "decision" | "resultat";
// neutre : fait établi ; alerte : geste hostile ; attente : bloqué en attente
// du SOC ; protege : rien n'est sorti ; libere : l'appel a été relâché.
export type TonMaillon = "neutre" | "alerte" | "attente" | "protege" | "libere" | "absent";

export interface MaillonAgent {
  cle: CleMaillon;
  lib: string;
  nature?: string; // précision du maillon : « mail lu par l'agent »
  titre: string;
  texte?: string;
  preuve?: string;
  preuveLib?: string;
  horodatage?: string;
  horoLib?: string; // ce que date l'heure affichée (« retenu à »)
  ton: TonMaillon;
  refs: Ref[];
  ids: string[];
  enCours?: boolean; // décision en attente : chrono vivant
}

export interface AppelCible {
  outil: string;
  preuve: string;
  horodatage?: string;
  scope?: string;
  horsJeton: boolean;
}

export type Issue = "attente" | "coupee" | "reprise" | "bloquee" | "surveillee";

export interface LectureAgent {
  maillons: MaillonAgent[];
  appel: AppelCible | null;
  // Vrai si un appel est retenu par la passerelle et peut être libéré.
  appelLiberable: boolean;
  issue: Issue;
  detection?: string; // ISO : canari touché ou action hors droits
  derniereDecision?: Decision;
  scopesUtilises: string[];
  refs: Ref[];
  depuisJournal: boolean;
}

const LIB: Record<CleMaillon, string> = {
  source: "Source",
  consigne: "Consigne",
  intention: "Intention",
  appel: "Appel d'outil",
  decision: "Décision",
  resultat: "Résultat",
};

// Natures de canari qui marquent la source piégée (et la consigne qu'elle porte).
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

const SOURCE_PAR_SURFACE: Record<string, string> = {
  mail: "mail lu par l'agent",
  document: "document lu par l'agent",
  outil: "outil MCP consulté",
  appel: "transcription d'appel",
  chatbot: "message entrant",
  memoire: "mémoire long terme",
  agent: "message d'un autre agent",
};

const CONSIGNE_PAR_SURFACE: Record<string, string> = {
  mail: "Consigne cachée dans le mail",
  document: "Consigne cachée dans le document",
  appel: "Consigne cachée dans la transcription",
};

const CONSIGNE_PAR_NATURE: Record<string, string> = {
  consigne_cachee: "Consigne cachée dans le texte",
  canari_mail: "Consigne cachée dans le mail",
  canari_document: "Consigne cachée dans le document",
  outil_mcp_piege: "Consigne cachée dans la description de l'outil",
  canari_appel: "Consigne cachée dans la transcription",
  injection_chatbot: "Injection dans le message entrant",
  memoire_empoisonnee: "Fausse préférence glissée en mémoire",
  agent_usurpation: "Délégation sans signature valide",
};

// Repères par défaut quand le backend n'en fournit pas pour ce maillon.
const REFS_CONSIGNE: Record<string, string[]> = {
  consigne_cachee: ["ASI01", "AML.T0051"],
  canari_mail: ["ASI01", "AML.T0051"],
  canari_document: ["ASI01", "AML.T0051"],
  canari_appel: ["ASI01", "AML.T0051"],
  injection_chatbot: ["ASI01", "AML.T0051"],
  memoire_empoisonnee: ["ASI06", "AML.T0051"],
  outil_mcp_piege: ["ASI02", "AML.T0051"],
  agent_usurpation: ["ASI07"],
};

const LIB_EVENEMENT: Record<string, string> = {
  sortie_agent: "la réponse finale de l'agent",
  appel_outil: "un nouvel appel d'outil",
  leurre_touche: "un nouveau canari touché",
  riposte: "une riposte de la passerelle",
  entree_agent: "une nouvelle entrée",
};

const LIB_DECISION: Record<string, string> = {
  couper: "Coupé",
  valider_riposte: "Riposte validée",
  reprendre: "Repris",
  ignorer: "Ignoré",
  clore: "Clos",
};

function refsDe(ids: (string | undefined)[]): Ref[] {
  return ids.map((i) => (i ? lireRef(i) : null)).filter((r): r is Ref => r !== null);
}

function refsLeurre(l?: Leurre): Ref[] {
  if (!l) return [];
  return refsDe([...(l.risques ?? []), ...(l.techniques ?? [])]);
}

function refsMaillon(m?: MaillonChaine): Ref[] {
  if (!m) return [];
  return [
    ...(m.risques ?? []).map((r) => lireRef(r.id)),
    ...(m.techniques ?? []).map((t) => lireRef(t.id, t.cadre)),
  ].filter((r): r is Ref => r !== null);
}

function texteClair(v: unknown): string {
  if (typeof v !== "string") return "";
  return sansPrefixe(decoderEntites(v)).texte.trim();
}

function majuscule(t: string): string {
  return t ? t.charAt(0).toUpperCase() + t.slice(1) : t;
}

function horo(ev?: { horodatage?: string }): string | undefined {
  return ev?.horodatage ?? undefined;
}

function temps(iso?: string | null): number {
  if (!iso) return Number.NaN;
  return new Date(iso).getTime();
}

function details(ev?: Evenement): Record<string, unknown> {
  return (ev?.details ?? {}) as Record<string, unknown>;
}

function issueDe(inc: Incident, derniere?: Decision, bloqueeParPasserelle = false): Issue {
  if (inc.etat === "coupee") return "coupee";
  if (derniere && (derniere.action === "reprendre" || derniere.action === "ignorer")) return "reprise";
  if (inc.etat === "suspendue") return bloqueeParPasserelle ? "bloquee" : "attente";
  return "surveillee";
}

export function lireBoiteNoire(inc: Incident, leurres: Leurre[]): LectureAgent {
  const evs = [...(inc.evenements ?? [])].sort(
    (a, b) => (a.horodatage ?? "").localeCompare(b.horodatage ?? "") || a.id - b.id
  );
  const decisions = inc.decisions ?? [];
  const derniereDecision = decisions.length ? decisions[decisions.length - 1] : undefined;
  if (evs.length === 0) return depuisChaine(inc, derniereDecision);

  const parId = new Map(leurres.map((l) => [l.id, l]));
  const entree = evs.find((e) => e.type === "entree_agent");
  const appels = evs.filter((e) => e.type === "appel_outil");
  const touches = evs.filter((e) => e.type === "leurre_touche");
  const ripostes = evs.filter((e) => e.type === "riposte");
  const nature = (e: Evenement) =>
    e.leurre_nature ?? (e.leurre_id ? parId.get(e.leurre_id)?.nature : undefined) ?? "";

  const violationEv = appels.find((e) => details(e).violation_droits);
  const violation = violationEv ? (details(violationEv).violation_droits as Record<string, unknown>) : null;
  const usurpationEv = appels.find((e) => details(e).provenance_invalide);
  const usurpation = usurpationEv ? (details(usurpationEv).provenance_invalide as Record<string, unknown>) : null;
  const mcpEv = appels.find((e) => details(e).outil_mcp_suspect);

  const toucheSource =
    touches.find((e) => NATURES_SOURCE.has(nature(e))) ??
    touches.find((e) => String(details(e).type ?? "").startsWith("consigne_"));
  const leurreSource = toucheSource?.leurre_id ? parId.get(toucheSource.leurre_id) : undefined;
  const natSource = toucheSource ? nature(toucheSource) : "";

  const ripBlocage = ripostes.find((e) => /^bloquer_/.test(String(details(e).action ?? "")));
  const ripCoupure = ripostes.find((e) => details(e).action === "couper");

  const detection =
    horo(touches[0]) ?? horo(violationEv) ?? horo(usurpationEv) ?? inc.temps_session?.detecte_a ?? undefined;

  // Appel visé : l'appel refusé hors droits, sinon le dernier appel du même
  // outil que le canari touché, sinon le dernier appel avant la détection.
  const tDetection = temps(detection);
  const outilTouche = touches.find((e) => e.outil)?.outil ?? null;
  const avant = (e: Evenement) => Number.isNaN(tDetection) || temps(e.horodatage) <= tDetection;
  const appelEv =
    violationEv ??
    (outilTouche ? [...appels].reverse().find((e) => e.outil === outilTouche && avant(e)) : undefined) ??
    [...appels].reverse().find(avant);
  const appelDet = details(appelEv);
  const appel: AppelCible | null = appelEv
    ? {
        outil: appelEv.outil ?? String((violation?.outil as string) ?? "outil"),
        preuve: violation
          ? `${appelEv.outil ?? violation.outil}(…) · droit exigé ${String(violation.scope_requis ?? "?")}`
          : appelInerte(appelEv.outil ?? "outil", appelDet.parametres),
        horodatage: appelEv.horodatage,
        scope: String((violation?.scope_requis as string) ?? (appelDet.scope_requis as string) ?? "") || undefined,
        horsJeton: Boolean(violation),
      }
    : touches.length && !outilTouche
      ? { outil: "réponse finale", preuve: "sortie de l'agent retenue avant affichage", horodatage: horo(touches[0]), horsJeton: false }
      : null;

  const bloqueeParPasserelle = Boolean(ripBlocage);
  const issue = issueDe(inc, derniereDecision, bloqueeParPasserelle);
  const statutFerme = inc.statut === "clos" || inc.statut === "ignore";
  const appelLiberable = issue === "attente" && !statutFerme && appel !== null && !appel.horsJeton && !usurpation;

  const scopesUtilises = Array.from(
    new Set(
      appels
        .filter((e) => !details(e).violation_droits && typeof details(e).scope_requis === "string")
        .map((e) => String(details(e).scope_requis))
    )
  );

  const demande = texteClair(details(entree).texte);
  const tache = texteClair((details(entree).droits as Record<string, unknown> | undefined)?.tache);

  // 1. Source.
  let source: MaillonAgent;
  if (leurreSource || mcpEv || usurpation) {
    const surface = leurreSource?.surface ?? (mcpEv ? "outil" : usurpation ? "agent" : "");
    const emplacement = texteClair(leurreSource?.emplacement);
    const lecture =
      (surface === "outil" ? mcpEv : undefined) ??
      appels.find((e) => surface && (e.outil ?? "").includes(surface === "document" ? "document" : surface)) ??
      entree;
    source = {
      cle: "source",
      lib: LIB.source,
      nature: SOURCE_PAR_SURFACE[surface] ?? "contenu lu par l'agent",
      titre: majuscule(
        emplacement ||
          (mcpEv ? `outil MCP ${mcpEv.outil} (serveur ${String(details(mcpEv).serveur_mcp ?? "?")})` : "") ||
          (usurpation ? `délégation reçue de « ${texteClair(usurpation.agent_pretendu)} »` : "contenu non identifié")
      ),
      texte: demande ? `Lu pendant la tâche « ${demande} »` : undefined,
      horodatage: horo(lecture),
      horoLib: lecture === entree ? "reçu à" : "lu à",
      ton: "neutre",
      refs: [],
      ids: leurreSource ? [leurreSource.id] : [],
    };
  } else {
    source = {
      cle: "source",
      lib: LIB.source,
      nature: "tâche confiée",
      titre: demande ? `« ${demande} »` : "Demande de l'agent non journalisée",
      texte: tache ? `Jeton émis pour la tâche ${tache}.` : undefined,
      horodatage: horo(entree),
      ton: entree ? "neutre" : "absent",
      refs: [],
      ids: [],
    };
  }

  // 2. Consigne.
  let consigne: MaillonAgent;
  if (leurreSource || toucheSource || mcpEv || usurpation) {
    const nat = natSource || (mcpEv ? "outil_mcp_piege" : usurpation ? "agent_usurpation" : "");
    const descr = leurreSource?.description ?? (mcpEv ? details(mcpEv).consigne_outil : undefined) ??
      (usurpation ? usurpation.raison : undefined) ?? details(toucheSource).detail;
    consigne = {
      cle: "consigne",
      lib: LIB.consigne,
      titre:
        (nat === "consigne_cachee" ? CONSIGNE_PAR_SURFACE[leurreSource?.surface ?? ""] : undefined) ??
        CONSIGNE_PAR_NATURE[nat] ??
        "Consigne étrangère à la tâche",
      texte: leurreSource && leurreSource.humain_visible === false ? "Un humain qui lit ce contenu ne la voit pas." : undefined,
      preuve: preuveInerte(descr),
      preuveLib: "Constat neutralisé",
      horodatage: horo(toucheSource) ?? horo(mcpEv) ?? horo(usurpationEv),
      horoLib: toucheSource ? "suivie à" : "vue à",
      ton: "alerte",
      refs: fusionnerRefs(refsLeurre(leurreSource), refsDe(REFS_CONSIGNE[nat] ?? [])),
      ids: leurreSource ? [leurreSource.id] : [],
    };
  } else {
    consigne = {
      cle: "consigne",
      lib: LIB.consigne,
      titre: "Aucune consigne piégée relevée",
      texte: violation
        ? "Aucun canari de consigne touché : l'agent sort seul du périmètre de sa tâche."
        : "Aucun canari de consigne touché dans cette session.",
      ton: "absent",
      refs: [],
      ids: [],
    };
  }

  // 3. Intention.
  const exfil = touches.find((e) => details(e).type === "exfiltration_markdown");
  const secret = touches.find((e) => nature(e) === "faux_secret" || details(e).type === "faux_secret");
  let intention: MaillonAgent;
  if (violation) {
    intention = {
      cle: "intention",
      lib: LIB.intention,
      titre: `Exécuter ${String(violation.outil ?? appel?.outil ?? "un outil")} sans en avoir le droit`,
      texte: `L'outil exige ${String(violation.scope_requis ?? "?")}. Le jeton de la tâche ne le porte pas.`,
      preuve: `jeton de tâche : ${((violation.scopes_jeton as string[] | undefined) ?? []).join(", ") || "vide"}`,
      preuveLib: "Constat de la passerelle",
      horodatage: horo(violationEv),
      horoLib: "tentée à",
      ton: "alerte",
      refs: refsDe(["ASI03"]),
      ids: [],
    };
  } else if (exfil || secret) {
    const domaine = exfil ? domaineExterne(String(details(exfil).detail ?? "")) : null;
    const idSecret = secret?.leurre_id ?? "";
    const titre = exfil && secret
      ? `Faire sortir la fausse clé ${idSecret} vers ${domaine ?? "un domaine externe"}`
      : exfil
        ? `Faire sortir des données vers ${domaine ?? "un domaine externe"}`
        : `Placer la fausse clé ${idSecret} dans sa sortie`;
    const leurreSecret = secret?.leurre_id ? parId.get(secret.leurre_id) : undefined;
    intention = {
      cle: "intention",
      lib: LIB.intention,
      titre,
      texte: exfil
        ? `Lien ou image vers ce domaine, glissé dans ${appel?.outil ?? "la sortie"}.`
        : "Un humain ne recopie jamais cette clé : seul un agent détourné le fait.",
      preuve: [exfil, secret].filter(Boolean).map((e) => preuveInerte(details(e).detail, 200)).join(" · "),
      preuveLib: "Constat de la passerelle, neutralisé",
      horodatage: horo(exfil ?? secret),
      horoLib: "relevée à",
      ton: "alerte",
      refs: fusionnerRefs(refsLeurre(leurreSecret), refsDe(["AML.T0057"])),
      ids: leurreSecret ? [leurreSecret.id] : [],
    };
  } else if (usurpation) {
    intention = {
      cle: "intention",
      lib: LIB.intention,
      titre: `Obéir à « ${texteClair(usurpation.agent_pretendu)} » sans vérifier qui parle`,
      texte: "La signature de la délégation est absente ou fausse.",
      horodatage: horo(usurpationEv),
      ton: "alerte",
      refs: refsDe(["ASI07"]),
      ids: [],
    };
  } else if (toucheSource) {
    intention = {
      cle: "intention",
      lib: LIB.intention,
      titre: "Suivre la consigne au lieu de sa tâche",
      preuve: preuveInerte(details(toucheSource).detail, 200),
      preuveLib: "Constat de la passerelle, neutralisé",
      horodatage: horo(toucheSource),
      ton: "alerte",
      refs: [],
      ids: [],
    };
  } else {
    intention = {
      cle: "intention",
      lib: LIB.intention,
      titre: "Intention non établie",
      texte: "Aucun canari ni action hors droits dans le journal.",
      ton: "absent",
      refs: [],
      ids: [],
    };
  }

  // 4. Appel d'outil.
  const tonAppel: TonMaillon =
    issue === "attente" ? "attente" : issue === "reprise" ? "libere" : issue === "surveillee" ? "neutre" : "protege";
  const appelMaillon: MaillonAgent = appel
    ? {
        cle: "appel",
        lib: LIB.appel,
        titre: appel.outil,
        texte: appel.scope
          ? appel.horsJeton
            ? `Droit exigé : ${appel.scope}, absent du jeton.`
            : `Droit utilisé : ${appel.scope}, présent dans le jeton.`
          : undefined,
        preuve: appel.preuve,
        horoLib: "appelé à",
        preuveLib:
          appel.horsJeton || bloqueeParPasserelle
            ? "Appel refusé par la passerelle"
            : issue === "reprise"
              ? "Appel libéré après décision"
              : issue === "coupee"
                ? "Appel jamais exécuté"
                : "Appel retenu par la passerelle",
        horodatage: appel.horodatage,
        ton: tonAppel,
        refs: refsDe(appel.horsJeton ? ["ASI02", "ASI03"] : ["ASI02"]),
        ids: [],
      }
    : {
        cle: "appel",
        lib: LIB.appel,
        titre: "Aucun appel d'outil relevé",
        ton: "absent",
        refs: [],
        ids: [],
      };

  // 5. Décision.
  const passerelle = appel?.horsJeton
    ? "La passerelle refuse l'appel et révoque le jeton de la tâche."
    : usurpation
      ? "La passerelle bloque la délégation."
      : "La passerelle retient l'appel et suspend la session.";
  const decision: MaillonAgent = derniereDecision
    ? {
        cle: "decision",
        lib: LIB.decision,
        titre: `${LIB_DECISION[derniereDecision.action] ?? derniereDecision.action} par ${derniereDecision.analyste}`,
        texte: appel?.horsJeton
          ? "La passerelle avait refusé l'appel et révoqué le jeton."
          : usurpation
            ? "La passerelle avait bloqué la délégation."
            : `La passerelle avait retenu l'appel${detection ? ` à ${new Date(detection).toLocaleTimeString("fr-FR")}` : ""}.`,
        horodatage: derniereDecision.horodatage,
        horoLib: "décidé à",
        ton: derniereDecision.action === "reprendre" || derniereDecision.action === "ignorer" ? "libere" : "protege",
        refs: [],
        ids: [],
      }
    : {
        cle: "decision",
        lib: LIB.decision,
        titre: statutFerme ? "Dossier fermé sans décision journalisée" : "En attente du SOC",
        texte: passerelle,
        horodatage: detection,
        horoLib: "retenu à",
        ton: statutFerme ? "neutre" : "attente",
        refs: [],
        ids: [],
        enCours: !statutFerme && (issue === "attente" || issue === "bloquee"),
      };

  // 6. Résultat : ce qui s'est réellement passé, d'après l'état et le journal.
  const tDecision = temps(derniereDecision?.horodatage);
  const apresDecision = Number.isNaN(tDecision) ? [] : evs.filter((e) => temps(e.horodatage) > tDecision);
  const nomAppel = appel?.outil ?? "L'appel";
  let resultat: MaillonAgent;
  if (issue === "coupee") {
    resultat = {
      cle: "resultat",
      lib: LIB.resultat,
      titre: "Session coupée, jeton révoqué",
      texte: ripCoupure || ripBlocage
        ? `${nomAppel} n'a pas été exécuté. Révocation confirmée par la passerelle.`
        : `${nomAppel} n'a pas été exécuté. Confirmation de la passerelle pas encore reçue.`,
      horodatage: horo(ripCoupure) ?? inc.temps_session?.confine_a ?? derniereDecision?.horodatage,
      horoLib: ripCoupure ? "confirmé à" : "coupé à",
      ton: "protege",
      refs: [],
      ids: [],
    };
  } else if (issue === "reprise") {
    resultat = {
      cle: "resultat",
      lib: LIB.resultat,
      titre: "Appel libéré, session reprise",
      texte: apresDecision.length
        ? `La passerelle a laissé passer ${nomAppel}. Reçu ensuite : ${LIB_EVENEMENT[apresDecision[apresDecision.length - 1].type] ?? apresDecision[apresDecision.length - 1].type}.`
        : `${nomAppel} est libéré. La passerelle n'a rien renvoyé depuis la décision.`,
      horodatage: horo(apresDecision[apresDecision.length - 1]) ?? derniereDecision?.horodatage,
      horoLib: apresDecision.length ? "reçu à" : "libéré à",
      ton: "libere",
      refs: [],
      ids: [],
    };
  } else if (issue === "bloquee") {
    resultat = {
      cle: "resultat",
      lib: LIB.resultat,
      titre: "Appel jamais exécuté",
      texte: `${nomAppel} n'est pas parti et le jeton est révoqué. Reprendre ne débloque pas une action hors droits.`,
      horodatage: horo(ripBlocage),
      horoLib: "révoqué à",
      ton: "protege",
      refs: [],
      ids: [],
    };
  } else if (issue === "attente") {
    resultat = {
      cle: "resultat",
      lib: LIB.resultat,
      titre: "Rien n'est sorti pour l'instant",
      texte: "L'appel reste bloqué tant que le SOC n'a pas tranché.",
      horoLib: "en cours",
      ton: "attente",
      refs: [],
      ids: [],
    };
  } else {
    resultat = {
      cle: "resultat",
      lib: LIB.resultat,
      titre: "Session active, sous surveillance",
      texte: "Aucun appel n'est retenu pour cette session.",
      ton: "neutre",
      refs: [],
      ids: [],
    };
  }

  const maillons = [source, consigne, intention, appelMaillon, decision, resultat];
  return {
    maillons,
    appel,
    appelLiberable,
    issue,
    detection,
    derniereDecision,
    scopesUtilises,
    refs: fusionnerRefs(...maillons.map((m) => m.refs)),
    depuisJournal: true,
  };
}

// Repli sans journal : on range la chaîne du backend dans les six maillons.
function depuisChaine(inc: Incident, derniere?: Decision): LectureAgent {
  const chaine = [...(inc.chaine ?? [])].sort((a, b) => a.ordre - b.ordre);
  const de = (phase: string) => chaine.filter((m) => m.phase === phase);
  const premier = (phase: string) => de(phase)[0];
  const dernier = (phase: string) => de(phase).slice(-1)[0];
  const issue = issueDe(inc, derniere);
  const statutFerme = inc.statut === "clos" || inc.statut === "ignore";
  const depuis = (
    cle: CleMaillon,
    m: MaillonChaine | undefined,
    ton: TonMaillon,
    vide: string
  ): MaillonAgent =>
    m
      ? {
          cle,
          lib: LIB[cle],
          titre: preuveInerte(m.titre, 120),
          preuve: preuveInerte(m.detail),
          preuveLib: "Extrait neutralisé",
          horodatage: m.horodatage,
          ton,
          refs: fusionnerRefs(refsMaillon(m)),
          ids: [m.canari_id, m.leurre_id].filter((x): x is string => Boolean(x)).slice(0, 1),
        }
      : { cle, lib: LIB[cle], titre: vide, ton: "absent", refs: [], ids: [] };

  const outil = dernier("outil");
  const maillons: MaillonAgent[] = [
    depuis("source", premier("entree"), "neutre", "Source non journalisée"),
    depuis("consigne", premier("consigne"), "alerte", "Aucune consigne piégée relevée"),
    depuis("intention", premier("sortie"), "alerte", "Intention non établie"),
    depuis("appel", outil, issue === "attente" ? "attente" : issue === "reprise" ? "libere" : "protege", "Aucun appel d'outil relevé"),
    derniere
      ? {
          cle: "decision",
          lib: LIB.decision,
          titre: `${LIB_DECISION[derniere.action] ?? derniere.action} par ${derniere.analyste}`,
          horodatage: derniere.horodatage,
          ton: derniere.action === "reprendre" || derniere.action === "ignorer" ? "libere" : "protege",
          refs: [],
          ids: [],
        }
      : {
          cle: "decision",
          lib: LIB.decision,
          titre: statutFerme ? "Dossier fermé" : "En attente du SOC",
          texte: "La passerelle retient l'appel et suspend la session.",
          horodatage: premier("consigne")?.horodatage ?? outil?.horodatage,
          ton: statutFerme ? "neutre" : "attente",
          refs: [],
          ids: [],
          enCours: !statutFerme && issue === "attente",
        },
    {
      cle: "resultat",
      lib: LIB.resultat,
      titre:
        issue === "coupee"
          ? "Session coupée, jeton révoqué"
          : issue === "reprise"
            ? "Appel libéré, session reprise"
            : issue === "attente"
              ? "Rien n'est sorti pour l'instant"
              : "Session active, sous surveillance",
      texte:
        issue === "attente"
          ? "L'appel reste bloqué tant que le SOC n'a pas tranché."
          : issue === "coupee"
            ? "L'appel retenu n'a pas été exécuté."
            : undefined,
      horodatage: issue === "coupee" || issue === "reprise" ? derniere?.horodatage : undefined,
      horoLib: issue === "attente" ? "en cours" : issue === "coupee" ? "coupé à" : issue === "reprise" ? "repris à" : undefined,
      ton: issue === "coupee" ? "protege" : issue === "reprise" ? "libere" : issue === "attente" ? "attente" : "neutre",
      refs: [],
      ids: [],
    },
  ];
  return {
    maillons,
    appel: outil
      ? { outil: "l'appel d'outil", preuve: preuveInerte(outil.detail), horodatage: outil.horodatage, horsJeton: false }
      : null,
    appelLiberable: issue === "attente" && !statutFerme && Boolean(outil),
    issue,
    detection: premier("consigne")?.horodatage ?? outil?.horodatage,
    derniereDecision: derniere,
    scopesUtilises: [],
    refs: fusionnerRefs(...maillons.map((m) => m.refs)),
    depuisJournal: false,
  };
}
