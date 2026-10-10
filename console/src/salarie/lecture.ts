// Geste d'un salarié, lu pour l'écran : la chaîne du backend parle en codes
// (« action risquée détectée », « passé outre »). On la réécrit en phrases
// simples, selon ce qu'il faisait : mail reçu, lien cliqué, pièce jointe,
// copier-coller, mail sortant, dépôt de fichier. Les détails viennent de
// l'avertissement du poste (`details` de l'événement), relié à chaque étape
// par `evenement_id`. Tout texte venu du poste est désarmé avant affichage.

import type { Decision, Evenement, Incident, MaillonChaine } from "../types";
import type { Brut, DetailMaillon, MaillonAgent, TonMaillon } from "../agent/boiteNoire";
import { desarmer, preuveInerte } from "../agent/preuve";
import { fusionnerRefs, lireRef } from "../agent/references";
import { sansCodes } from "../ui/mots";

export type Genre =
  | "mail_recu" | "lien" | "piece" | "coller" | "mail_sortant" | "depot" | "signal" | "fichier"
  | "virement" | "export" | "autre";

const PAR_CONTEXTE: Record<string, Genre> = {
  "mail reçu": "mail_recu",
  "navigation web": "lien",
  navigation: "lien",
  signalement: "signal",
  telechargement: "fichier",
  "pièce jointe": "piece",
  "copier-coller": "coller",
  "mail sortant": "mail_sortant",
  "dépôt de fichier": "depot",
};

const PAR_TYPE: Record<string, Genre> = {
  humain_phishing: "lien",
  humain_secret: "coller",
  humain_mail_externe: "mail_sortant",
  humain_upload_ia: "depot",
  humain_signalement: "signal",
};

type Details = Record<string, unknown>;

function texte(v: unknown): string {
  return typeof v === "string" ? desarmer(v).trim() : "";
}

function genreDe(d: Details, type?: string): Genre {
  // Geste critique : le récit suit le geste (champ structuré), pas la catégorie de l'alerte.
  // Un virement réclamé par mail est classé « phishing », mais personne n'a cliqué de lien.
  if (d.geste === "virement") return "virement";
  if (d.geste === "export_clients") return "export";
  const ctx = typeof d.contexte === "string" ? d.contexte : "";
  return PAR_CONTEXTE[ctx] ?? PAR_TYPE[type ?? ""] ?? "autre";
}

// Ce qu'il faisait au moment du geste.
const CONTEXTE: Record<Genre, string> = {
  mail_recu: "Un mail est arrivé dans sa boîte",
  lien: "Il naviguait sur le web",
  piece: "Un mail avec une pièce jointe est arrivé",
  coller: "Il travaillait dans un outil en ligne",
  mail_sortant: "Il écrivait un mail",
  depot: "Il préparait un dépôt de fichier",
  signal: "Un mail est arrivé dans sa boîte",
  fichier: "Un fichier est arrivé dans ses Téléchargements",
  virement: "Il préparait un virement",
  export: "Il préparait un export de données clients",
  autre: "Sur son poste",
};

// Le geste risqué, en titre court.
const GESTE: Record<Genre, string> = {
  mail_recu: "Il a ouvert un mail frauduleux",
  lien: "Il a cliqué sur un faux site d'Orbis Pay",
  piece: "Il a voulu ouvrir une pièce jointe piégée",
  coller: "Il a voulu coller une clé secrète",
  mail_sortant: "Il envoyait des données à l'extérieur",
  depot: "Il déposait un fichier confidentiel en ligne",
  signal: "Il a signalé un mail",
  fichier: "Il a téléchargé un fichier à risque",
  virement: "Il a demandé un virement",
  export: "Il a demandé un export de données clients",
  autre: "Il a fait un geste risqué",
};

const POURQUOI: Record<Genre, string> = {
  mail_recu: "Le mail a les marques d'une fraude : son expéditeur, ses liens ou sa demande ne collent pas.",
  lien: "Le lien mène à un site qui imite Orbis Pay sans en faire partie.",
  piece: "Le fichier a les marques d'une pièce jointe piégée.",
  coller: "Dédale a reconnu une clé secrète dans ce que le salarié allait coller.",
  mail_sortant: "Le destinataire est hors de l'entreprise et le mail contient des données sensibles.",
  depot: "Ce service n'est pas validé par Orbis Pay et le fichier est confidentiel.",
  signal: "Le salarié a jugé ce mail suspect et l'a signalé lui-même.",
  fichier: "Le fichier peut lancer un programme et vient de l'extérieur.",
  virement: "Un virement est un geste critique : il ne part qu'avec une double validation.",
  export: "Un export de données clients est un geste critique : il ne part qu'avec une double validation.",
  autre: "Dédale a reconnu un geste qui expose l'entreprise.",
};

const RISQUE: Record<Genre, string> = {
  mail_recu: "En suivant le lien, le salarié aurait donné son mot de passe à un faux site.",
  lien: "Le salarié aurait tapé son mot de passe sur un faux site.",
  piece: "Le fichier aurait pu installer un logiciel malveillant sur le poste.",
  coller: "La clé aurait été exposée à un service extérieur, sans retour possible.",
  mail_sortant: "Les données seraient sorties de l'entreprise.",
  depot: "Le fichier serait stocké chez un service que l'entreprise ne contrôle pas.",
  signal: "Un mail frauduleux non signalé peut piéger d'autres salariés.",
  fichier: "Le programme se serait lancé sur le poste.",
  virement: "L'argent serait parti sans second contrôle.",
  export: "Les données clients seraient sorties sans second contrôle.",
  autre: "Le geste aurait pu exposer des données de l'entreprise.",
};

// Le salarié a continué : rien ne l'a arrêté. On dit ce qui a pu se passer, au
// présent, sans affirmer plus que ce que Dédale a vu.
const RISQUE_PASSE: Record<Genre, string> = {
  mail_recu: "Le mot de passe a peut-être été saisi sur le faux site.",
  lien: "Le mot de passe a peut-être été saisi sur le faux site.",
  piece: "Le fichier a peut-être été ouvert sur le poste.",
  coller: "La clé a peut-être été collée sur le service extérieur.",
  mail_sortant: "Les données sont peut-être sorties de l'entreprise.",
  depot: "Le fichier est peut-être déjà chez un service que l'entreprise ne contrôle pas.",
  signal: "Le mail est peut-être arrivé chez d'autres salariés.",
  fichier: "Le fichier est resté sur le poste : il a peut-être été ouvert.",
  virement: "Le virement reste suspendu tant qu'il n'est pas validé.",
  export: "L'export reste suspendu tant qu'il n'est pas validé.",
  autre: "Le geste a peut-être exposé des données de l'entreprise.",
};
const TITRE_PASSE = "Ce qui a pu se passer";

// Le geste en une phrase, pour l'encadré « Le geste ».
function phraseGeste(g: Genre, d: Details): string {
  const de = texte(d.expediteur);
  const affiche = texte(d.expediteur_affiche);
  const fichier = texte(d.fichier);
  const cible = texte(d.cible);
  switch (g) {
    case "mail_recu":
      return affiche && de
        ? `Le salarié a ouvert un mail signé « ${affiche} », envoyé en réalité par ${de}. Son lien mène à un faux site.`
        : "Le salarié a ouvert un mail frauduleux malgré l'alerte de Dédale.";
    case "lien":
      return "Le salarié a cliqué sur un lien qui mène à un faux site d'Orbis Pay.";
    case "piece":
      return fichier
        ? `Le salarié a voulu ouvrir « ${fichier} », une pièce jointe piégée.`
        : "Le salarié a voulu ouvrir une pièce jointe piégée.";
    case "coller":
      return cible
        ? `Le salarié a voulu coller une clé secrète dans ${cible}, hors de l'entreprise.`
        : "Le salarié a voulu coller une clé secrète hors de l'entreprise.";
    case "mail_sortant":
      return "Le salarié a voulu envoyer des données de l'entreprise à une adresse extérieure.";
    case "depot":
      return fichier && cible
        ? `Le salarié a voulu déposer « ${fichier} », un fichier confidentiel, sur ${cible}.`
        : "Le salarié a voulu déposer un fichier confidentiel sur un service non autorisé.";
    case "signal":
      return "Le salarié a signalé lui-même un mail qu'il trouvait suspect.";
    case "virement":
      return "Le salarié a demandé un virement, soumis à double validation.";
    case "export":
      return "Le salarié a demandé un export de données clients, soumis à double validation.";
    case "fichier": {
      const quoi = TYPES_FICHIER[String(d.type_fichier ?? "")] ?? "un fichier à risque";
      const dom = texte(d.domaine);
      const garde = d.choix === "annuler" ? "mis de côté" : "gardé";
      return `${quoi.charAt(0).toUpperCase()}${quoi.slice(1)} téléchargé${dom ? ` depuis ${dom}` : ""} et ${garde} par le salarié.`;
    }
    default:
      return "Le salarié a fait un geste risqué sur son poste.";
  }
}

// Ce qui précise le geste, sous son titre.
function texteGeste(g: Genre, d: Details): string | undefined {
  const lien = texte(d.lien) || texte(d.url);
  const fichier = texte(d.fichier);
  const cible = texte(d.cible);
  switch (g) {
    case "mail_recu": {
      const de = texte(d.expediteur);
      const affiche = texte(d.expediteur_affiche);
      return affiche && de ? `Signé « ${affiche} », il est envoyé par ${de}.` : de ? `Il est envoyé par ${de}.` : undefined;
    }
    case "lien":
      return lien ? `Le lien mène à ${lien}.` : undefined;
    case "piece":
      if (!fichier) return undefined;
      return d.expediteur_externe ? `« ${fichier} » vient d'un expéditeur extérieur.` : `Le fichier s'appelle « ${fichier} ».`;
    case "coller":
      return cible ? `Il voulait la coller dans ${cible}.` : undefined;
    case "mail_sortant": {
      const dest = Array.isArray(d.destinataires_externes) ? d.destinataires_externes.map(texte).filter(Boolean).join(", ") : "";
      return dest ? `Le mail part vers ${dest}.` : undefined;
    }
    case "depot":
      return fichier && cible ? `« ${fichier} » vers ${cible}.` : undefined;
    case "fichier": {
      const quoi = TYPES_FICHIER[String(d.type_fichier ?? "")] ?? "un fichier";
      const dom = texte(d.domaine);
      const sha = typeof d.sha256 === "string" && /^[0-9a-f]{12,}$/i.test(d.sha256) ? d.sha256.slice(0, 12).toLowerCase() : "";
      return `${quoi.charAt(0).toUpperCase()}${quoi.slice(1)}${dom ? ` venu de ${dom}` : ""}${sha ? `, empreinte ${sha}…` : ""}.`;
    }
    default:
      return undefined;
  }
}

// Type d'un fichier téléchargé (app Mac), avec son article. Jamais son nom.
const TYPES_FICHIER: Record<string, string> = {
  application: "un programme",
  script: "un script",
  image_disque: "une image disque",
  installeur: "un installeur",
  raccourci: "un raccourci",
  document_macros: "un document à macros",
  archive_chiffree: "une archive chiffrée",
  document: "un document",
};
const PROVENANCES: Record<string, string> = {
  mail: "un mail",
  site: "un site",
  messagerie: "une messagerie",
  airdrop: "AirDrop",
  inconnue: "inconnue",
  locale: "le poste lui-même",
};

function brutsFichier(d: Details): Brut[] {
  const sha = typeof d.sha256 === "string" && /^[0-9a-f]{12,}$/i.test(d.sha256) ? `${d.sha256.slice(0, 16).toLowerCase()}…` : "";
  return [
    { lib: "Type", valeur: TYPES_FICHIER[String(d.type_fichier ?? "")] ?? "" },
    { lib: "Domaine d'origine", valeur: texte(d.domaine), mono: true },
    { lib: "Arrivé par", valeur: PROVENANCES[String(d.provenance ?? "")] ?? "" },
    { lib: "Empreinte SHA-256", valeur: sha, mono: true },
    { lib: "Choix", valeur: d.choix === "annuler" ? "mis de côté" : d.choix === "continuer" ? "gardé" : "" },
  ].filter((b) => b.valeur);
}

function brutsGeste(g: Genre, d: Details): Brut[] {
  if (g === "fichier") return brutsFichier(d);
  const lignes: [string, unknown, boolean?][] = [
    ["Expéditeur affiché", d.expediteur_affiche],
    ["Adresse réelle", d.expediteur, true],
    ["Objet", d.objet],
    ["Lien", d.lien ?? d.url, true],
    ["Fichier", d.fichier, true],
    ["Où", d.cible],
    ["Destinataires", Array.isArray(d.destinataires_externes) ? d.destinataires_externes.join(", ") : undefined, true],
    ["Ce que Dédale a repéré", d.categorie_secret ?? d.indice],
  ];
  return lignes
    .map(([lib, v, mono]) => ({ lib, valeur: texte(v), mono: Boolean(mono) }))
    .filter((b) => b.valeur && !(g === "mail_recu" && b.lib === "Où"));
}

export interface MessageAffiche {
  titre: string;
  explication: string;
  lien: string; // lien ou fichier en cause, désarmé ; vide sinon
}

export interface LectureSalarie {
  geste?: string;
  message?: MessageAffiche;
  maillons: MaillonAgent[];
}

const LIB: Record<string, string> = {
  contexte: "Contexte",
  entree: "Contexte",
  action_risquee: "Geste risqué",
  signalement: "Signalement",
  avertissement: "Alerte de Dédale",
  choix: "Choix du salarié",
  consequence: "Suite",
  sortie: "Suite",
  riposte: "Suite",
};

const ICONE: Record<string, string> = {
  contexte: "ecran",
  entree: "ecran",
  action_risquee: "curseur",
  signalement: "signal",
  avertissement: "bouclier",
  choix: "choix",
  consequence: "resultat",
  sortie: "resultat",
  riposte: "resultat",
};

const DECISION: Record<string, string> = {
  clore: "L'analyste a clos le dossier",
  ignorer: "L'analyste a classé le dossier sans suite",
  accorder: "L'analyste a accordé le geste",
  refuser: "L'analyste a refusé le geste",
};

const REMEDIATION: Record<string, string> = {
  reinitialiser_mot_de_passe: "Mot de passe réinitialisé",
  fermer_sessions: "Sessions fermées",
  bloquer_domaine: "Domaine bloqué pour tous",
};

function refsDe(m: MaillonChaine) {
  return fusionnerRefs(
    (m.risques ?? []).map((r) => lireRef(r.id)),
    (m.techniques ?? []).map((t) => {
      const r = lireRef(t.id, t.cadre);
      return r ? { ...r, nom: t.nom } : null;
    })
  );
}

export function lireGesteSalarie(inc: Incident): LectureSalarie {
  // Heures comparées en temps réel : les modules n'écrivent pas tous le même fuseau.
  const t = (iso?: string) => (iso ? Date.parse(iso) || 0 : 0);
  const chaine = [...(inc.chaine ?? [])].sort((a, b) => t(a.horodatage) - t(b.horodatage) || a.ordre - b.ordre);
  const evs = new Map<number, Evenement>((inc.evenements ?? []).map((e) => [e.id, e]));
  const avertissements = (inc.evenements ?? []).filter((e) => e.type === "avertissement");
  // L'avertissement qui a fait remonter le dossier : le dernier passé outre,
  // sinon le dernier tout court.
  const principal =
    [...avertissements].reverse().find((e) => (e.details as Details | undefined)?.choix === "continuer") ??
    avertissements[avertissements.length - 1];
  const dPrincipal = (principal?.details ?? {}) as Details;
  const genrePrincipal = genreDe(dPrincipal, inc.type);
  const ferme = inc.statut === "clos" || inc.statut === "ignore";

  // Détails de l'avertissement lié à une étape ; le contexte prend celui qui suit.
  const detailsDe = (m: MaillonChaine, k: number): Details => {
    const e = m.evenement_id != null ? evs.get(m.evenement_id) : undefined;
    if (e?.type === "avertissement") return (e.details ?? {}) as Details;
    const suivant = etapes.slice(k + 1).find((x) => x.evenement_id != null && evs.get(x.evenement_id)?.type === "avertissement");
    const ev = suivant?.evenement_id != null ? evs.get(suivant.evenement_id) : undefined;
    return (ev?.details ?? dPrincipal) as Details;
  };

  // Une seule « Suite » par geste : le backend en pose parfois plusieurs d'affilée (geste
  // suspendu, relu, tranché). On garde la dernière, qui dit l'état réel.
  const etapes = chaine.filter(
    (m, k) => !((m.phase === "consequence" || m.phase === "sortie") && (chaine[k + 1]?.phase === "consequence" || chaine[k + 1]?.phase === "sortie"))
  );
  const maillons: MaillonAgent[] = etapes.map((m, k) => {
    const d = detailsDe(m, k);
    const g = genreDe(d, inc.type);
    const observe = sansCodes(desarmer(m.detail ?? ""));
    const base = {
      cle: "source" as const,
      id: `sal-${m.ordre}-${k}`,
      lib: LIB[m.phase] ?? "Étape",
      horodatage: m.horodatage,
      icone: ICONE[m.phase] ?? "resultat",
    };
    const refs = refsDe(m);
    switch (m.phase) {
      case "contexte":
      case "entree":
        return {
          ...base,
          titre: CONTEXTE[g],
          texte: observe || undefined,
          ton: "neutre" as TonMaillon,
          detail: {
            brut: observe ? [{ lib: "Observé sur le poste", valeur: observe }] : [],
            pourquoi: "Dédale suit ce qui se passe sur le poste sans rien bloquer.",
            refs,
          },
        };
      case "action_risquee": {
        const continue_ = d.choix === "continuer";
        return {
          ...base,
          titre: GESTE[g],
          texte: texteGeste(g, d),
          ton: "alerte" as TonMaillon,
          detail: {
            brut: brutsGeste(g, d),
            pourquoi: texte(d.raison) ? `${POURQUOI[g]} Indice : ${texte(d.raison)}.` : POURQUOI[g],
            risque: continue_ ? RISQUE_PASSE[g] : RISQUE[g],
            risqueTitre: continue_ ? TITRE_PASSE : undefined,
            refs,
          },
        };
      }
      case "signalement": {
        const verdict = /analyseur : (\S+)/.exec(observe)?.[1];
        return {
          ...base,
          titre: "Il a signalé ce mail lui-même",
          texte: verdict ? `L'analyseur de mails l'avait jugé ${verdict}.` : "Le mail part au SOC pour vérification.",
          ton: "protege" as TonMaillon,
          detail: {
            brut: [{ lib: "Ce qui est remonté", valeur: observe }],
            pourquoi: POURQUOI.signal,
            risque: RISQUE.signal,
            refs,
          },
        };
      }
      case "avertissement": {
        const titre = texte(d.titre);
        const explication = texte(d.explication);
        return {
          ...base,
          titre: "Dédale l'a prévenu",
          texte: titre ? `« ${titre} »` : "Une alerte s'est affichée sur son écran.",
          ton: "protege" as TonMaillon,
          detail: {
            brut: [
              ...(titre ? [{ lib: "Titre de l'alerte", valeur: titre }] : []),
              ...(explication ? [{ lib: "Message", valeur: explication }] : []),
              ...(typeof d.gravite === "string" ? [{ lib: "Gravité annoncée", valeur: d.gravite }] : []),
            ],
            pourquoi: "Dédale prévient au moment du geste, avant qu'il n'aboutisse.",
            risque: "Sans cette alerte, le salarié n'aurait rien vu passer.",
            refs,
          },
        };
      }
      case "choix": {
        const continue_ = d.choix === "continuer" || /continu|outre/i.test(m.detail ?? "");
        const fichier = g === "fichier";
        return {
          ...base,
          titre: continue_ ? (fichier ? "Il a gardé le fichier" : "Il a continué malgré l'alerte") : fichier ? "Il a mis le fichier de côté" : "Il a annulé son geste",
          texte: continue_
            ? fichier
              ? "Il a choisi « Garder » plutôt que « Mettre de côté »."
              : "Il a cliqué sur « Continuer quand même »."
            : fichier
              ? "Il a suivi l'alerte : le fichier est rangé à part."
              : "Il a suivi l'alerte et cliqué sur « Annuler ».",
          ton: (continue_ ? "alerte" : "protege") as TonMaillon,
          detail: {
            brut: [{ lib: "Choix", valeur: continue_ ? "continuer quand même" : "annuler" }],
            pourquoi: "Dédale ne bloque pas le poste : le salarié reste libre de choisir.",
            risque: continue_ ? RISQUE_PASSE[g] : undefined,
            risqueTitre: continue_ ? TITRE_PASSE : undefined,
            refs,
          },
        };
      }
      default: {
        // Geste suspendu, relu ou tranché : le backend dit son vrai état, on le reprend.
        const etat = /relu par Dédale|suspendu|refusé|accordé|aucune décision/i.test(observe) ? observe : "";
        const nAPasEuLieu = /refus|aucune décision/i.test(etat);
        const accorde = !nAPasEuLieu && /accord/i.test(etat);
        return {
          ...base,
          titre: etat
            ? nAPasEuLieu ? "Le geste n'a pas eu lieu" : accorde ? "Le geste a été accordé" : "Le geste attend une décision"
            : "Le dossier est arrivé au SOC",
          texte: etat || (g === "fichier" ? "Le fichier est resté sur le poste." : "Le geste a abouti malgré l'alerte."),
          ton: (etat ? (nAPasEuLieu ? "protege" : accorde ? "neutre" : "attente") : "neutre") as TonMaillon,
          detail: {
            brut: etat ? [{ lib: "État", valeur: etat }] : [],
            pourquoi: etat
              ? "Un geste critique ne part qu'avec une validation : du relecteur IA, puis de l'analyste."
              : "Le salarié a continué malgré l'alerte : le dossier remonte au SOC.",
            risque: etat ? undefined : RISQUE_PASSE[g],
            risqueTitre: etat ? undefined : TITRE_PASSE,
            refs,
          },
        };
      }
    }
  });

  // La décision de l'analyste : orange tant que le dossier attend, gris ensuite.
  const decisions: Decision[] = [...(inc.decisions ?? [])].sort((a, b) => t(a.horodatage) - t(b.horodatage));
  const journal = inc.journal_console ?? [];
  decisions.forEach((dec, i) => {
    const motif = journal.find(
      (j) => j.acte === "decision" && j.action === dec.action && (j.horodatage ?? "") >= (dec.horodatage ?? "")
    )?.motif;
    maillons.push({
      cle: "decision",
      id: `sal-decision-${i}`,
      lib: "Décision",
      titre: /^relecteur/i.test(dec.analyste)
        ? (DECISION[dec.action] ?? `Décision : ${dec.action}`).replace("L'analyste", "Le relecteur IA")
        : DECISION[dec.action] ?? `Décision : ${dec.action}`,
      texte: `Décision prise par ${dec.analyste.replace(/\.$/, "")}.${motif ? ` Motif : « ${motif} ».` : ""}`,
      horodatage: dec.horodatage,
      ton: dec.action === "refuser" ? "protege" : "neutre",
      detail: {
        brut: [{ lib: "Par", valeur: dec.analyste }, ...(motif ? [{ lib: "Motif", valeur: motif }] : [])],
        pourquoi: "Dédale prévient le salarié, l'analyste décide de la suite.",
        refs: [],
      },
    });
  });
  // Ce que le SOC a fait sur le compte ou le domaine : actions simulées, scellées.
  journal
    .filter((j) => j.acte === "remediation")
    .forEach((j, i) =>
      maillons.push({
        cle: "correctif",
        id: `sal-remediation-${i}`,
        lib: "Suite du SOC",
        icone: "correctif",
        titre: REMEDIATION[j.action ?? ""] ?? "Action du SOC",
        texte: j.message ? desarmer(j.message) : undefined,
        horodatage: j.horodatage,
        ton: "protege",
        detail: {
          brut: [
            { lib: "Par", valeur: j.analyste ?? "l'analyste" },
            ...(j.domaine ? [{ lib: "Domaine", valeur: desarmer(j.domaine), mono: true }] : []),
          ],
          pourquoi: "Action simulée dans cette démo, notée au journal scellé comme une vraie.",
          refs: [],
        },
      })
    );
  if (decisions.length === 0) {
    maillons.push({
      cle: "decision",
      id: "sal-decision-attente",
      lib: "Décision",
      titre: ferme ? "Dossier fermé" : "En attente de votre décision",
      texte: ferme ? undefined : inc.quatre_yeux && !inc.quatre_yeux.issue ? "Accorder ou refuser le geste." : "Clore le dossier ou le classer sans suite.",
      horodatage: undefined,
      ton: ferme ? "neutre" : "attente",
      detail: { brut: [], pourquoi: "Dédale prévient le salarié, l'analyste décide de la suite.", refs: [] } as DetailMaillon,
    });
  }

  const titreMsg = texte(dPrincipal.titre);
  const explication = texte(dPrincipal.explication);
  return {
    geste: principal ? phraseGeste(genrePrincipal, dPrincipal) : undefined,
    message:
      titreMsg || explication
        ? {
            titre: titreMsg,
            explication,
            lien: preuveInerte(dPrincipal.lien ?? dPrincipal.url ?? dPrincipal.fichier ?? "", 200),
          }
        : undefined,
    maillons,
  };
}
