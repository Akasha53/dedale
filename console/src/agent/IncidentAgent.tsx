// Écran d'un incident d'agent IA : ce qui s'est passé en deux ou trois
// phrases, la boîte noire étape par étape, et la décision (couper, laisser
// passer, retirer un droit). Tout le texte est en mots simples ; le contenu
// lu par l'agent s'ouvre en entier depuis l'étape « Lecture ».

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useDonnees } from "../api/store";
import type { DecisionAction, Incident } from "../types";
import { dureeCourte, lireBoiteNoire, type Issue, type LectureAgent, type MaillonAgent } from "./boiteNoire";
import { Icone, type NomIcone } from "./icones";
import { sourcePour } from "./sources";
import { SyntheseBloc, useSynthese } from "./Synthese";
import { ModaleSource } from "./ModaleSource";
import { DetailEtape, Depliant } from "./Depliant";
import { BadgeIntegrite, MenuExport } from "./OutilsDossier";
import { TexteCanary } from "../ui/Canary";
import { useAnalyste } from "../ui/analyste";
import { BandeauAnnulation, BlocConfirmation, estPetitEcran, useDifferee } from "../ui/Confirmation";
import { GRAVITE, libelleDroit, nomAgent, proprietaireAgent, titreIncident } from "../ui/mots";

// ---------- temps ----------

function useMaintenant(actif: boolean): number {
  const [t, setT] = useState(() => Date.now());
  useEffect(() => {
    if (!actif) return;
    const id = setInterval(() => setT(Date.now()), 1000);
    return () => clearInterval(id);
  }, [actif]);
  return t;
}

function ms(iso?: string | null): number {
  if (!iso) return Number.NaN;
  return new Date(iso).getTime();
}

// Durée lisible : millisecondes sous la seconde, puis secondes, minutes, heures.
export function duree(delta: number): string {
  if (!Number.isFinite(delta)) return "—";
  if (delta < 1) return "< 1 ms";
  if (delta < 1000) return `${Math.round(delta)} ms`;
  const s = delta / 1000;
  if (s < 60) return `${s.toFixed(s < 10 ? 1 : 0).replace(".", ",")} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ${String(Math.floor(s % 60)).padStart(2, "0")} s`;
  return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")} min`;
}

function Heure({ iso }: { iso?: string }) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return (
    <time className="ag-heure" dateTime={iso}>
      {d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
    </time>
  );
}

// ---------- état ----------

// Ce que l'écran affiche, une couleur par état : orange seulement quand un
// appel est suspendu et attend un humain, vert quand l'agent est arrêté ou
// l'action refusée, gris pour le reste.
export type EtatVue = "attente" | "refusee" | "coupee" | "reprise" | "close" | "classee" | "surveillee";

export function etatVue(incident: Incident, issue: Issue): EtatVue {
  if (incident.statut === "ignore") return "classee";
  if (issue === "coupee") return "coupee";
  if (incident.statut === "clos") return "close";
  if (issue === "bloquee") return "refusee";
  if (issue === "attente") return "attente";
  if (issue === "reprise") return "reprise";
  return "surveillee";
}

const ETAT: Record<EtatVue, { lib: string; cls: string }> = {
  attente: { lib: "À décider", cls: "attente" },
  refusee: { lib: "Refusée par Dédale", cls: "bloquee" },
  coupee: { lib: "Agent arrêté", cls: "coupee" },
  reprise: { lib: "Laissé passer, surveillé", cls: "reprise" },
  close: { lib: "Clos", cls: "surveillee" },
  classee: { lib: "Classé sans suite", cls: "surveillee" },
  surveillee: { lib: "En service, surveillé", cls: "surveillee" },
};

function PiluleEtat({ vue }: { vue: EtatVue }) {
  const e = ETAT[vue];
  return (
    <span className={`ag-etat ag-etat-${e.cls}`} key={vue}>
      <span className="ag-etat-point" />
      {e.lib}
    </span>
  );
}

// Résumé de repli quand le copilote du backend n'écrit rien pour ce type.
function repliAgent(lecture: LectureAgent, type?: string): string[] {
  const piege = lecture.maillons.find((m) => m.cle === "consigne");
  const resultat = lecture.maillons.find((m) => m.cle === "resultat");
  const fin = resultat ? `${resultat.titre}.` : "";
  if (type === "interne_desarme")
    return [
      "Un contenu venu de l'extérieur cachait une instruction pour l'agent. Dédale l'a retirée avant que l'agent le lise.",
      "L'agent a reçu la version propre et n'a rien suivi. Vous pouvez relire ce qui a été retiré, puis clore.",
    ];
  if (type === "interne_envoi_externe")
    return [
      "L'agent a voulu envoyer quelque chose à une adresse hors d'Orbis Pay. Dédale retient tout envoi vers l'extérieur avant qu'il parte.",
      `${lecture.enJeu} ${fin}`.trim(),
    ];
  if (type === "interne_politique")
    return ["Une règle écrite par le SOC s'est appliquée à une action de l'agent.", `${lecture.enJeu} ${fin}`.trim()];
  if (type === "interne_anomalie")
    return [
      "L'agent est sorti de son habitude de travail. Dédale le signale sans l'arrêter.",
      "Relisez l'écart dans la boîte noire, puis clorez le dossier ou coupez l'agent.",
    ];
  return [
    piege ? "L'agent a lu un contenu piégé qui lui demandait d'agir hors de sa tâche." : "L'agent a tenté une action hors de sa tâche.",
    `${lecture.enJeu} ${fin}`.trim(),
  ];
}

// ---------- composant principal ----------

export function IncidentAgent({
  incident,
  majEnCours,
  decisionEnCours,
  erreurDecision,
  trancher,
}: {
  incident: Incident;
  majEnCours: boolean;
  decisionEnCours: DecisionAction | null;
  erreurDecision: string | null;
  trancher: (a: DecisionAction, motif?: string) => void;
}) {
  const { leurres, sessions } = useDonnees();
  const lecture = useMemo(() => lireBoiteNoire(incident, leurres), [incident, leurres]);
  const { synthese, prete } = useSynthese(incident);
  const vue = etatVue(incident, lecture.issue);
  // Le compteur ne tourne que si un appel attend vraiment un humain.
  const maintenant = useMaintenant(vue === "attente");
  const [sourceOuverte, setSourceOuverte] = useState(false);
  const source = useMemo(() => sourcePour(incident), [incident]);
  const agent = sessions.find((s) => s.id === incident.session_id)?.agent;

  useEffect(() => setSourceOuverte(false), [incident.id]);
  const fermerSource = useCallback(() => setSourceOuverte(false), []);

  return (
    <div className="ag-dossier">
      <section className="ag-coque ag-entete" aria-labelledby="ag-titre">
        <div className="ag-noyau">
          <div className="ag-entete-haut">
            <span className={`gravite ${incident.gravite}`}>{GRAVITE[incident.gravite] ?? incident.gravite}</span>
            <PiluleEtat vue={vue} />
            <span className="ag-outils">
              <BadgeIntegrite incident={incident} />
              <MenuExport incident={incident} />
            </span>
          </div>
          <p className="ag-qui">
            <strong>{nomAgent(agent)}</strong>
            {proprietaireAgent(agent) && <span> · {proprietaireAgent(agent)}</span>}
            {lecture.detection && <span className="ag-meta"> · repéré à <Heure iso={lecture.detection} /></span>}
            {majEnCours ? <span className="ag-meta"> · mise à jour…</span> : null}
          </p>
          <h2 id="ag-titre" className="ag-titre">{titreIncident(incident)}</h2>
          <SyntheseBloc
            synthese={synthese}
            prete={prete}
            repli={repliAgent(lecture, incident.type)}
            libelles={lecture.prevenu && !lecture.appel ? { reprendre: "Remettre l'agent en service" } : undefined}
          />
          <Chrono incident={incident} lecture={lecture} vue={vue} maintenant={maintenant} />
        </div>
      </section>

      <div className="ag-grille">
        <FriseEtapes
          maillons={lecture.maillons}
          sourcil="Boîte noire"
          titre="Ce que l'agent a fait, étape par étape"
          idTitre="ag-chaine-titre"
          droite={<span className="ag-carte-note">touchez une étape pour le détail</span>}
          maintenant={maintenant}
          voir={VOIR[source.genre] ?? VOIR.document}
          ouvrirSource={() => setSourceOuverte(true)}
        />
        <PanneauDecision
          incident={incident}
          lecture={lecture}
          vue={vue}
          maintenant={maintenant}
          conseil={synthese?.decision_recommandee?.deja_appliquee ? null : synthese?.decision_recommandee?.action ?? null}
          droitSuggere={synthese?.correctif_suggere?.droit ?? null}
          decisionEnCours={decisionEnCours}
          erreurDecision={erreurDecision}
          trancher={trancher}
        />
      </div>

      {sourceOuverte && <ModaleSource incident={incident} fermer={fermerSource} />}
    </div>
  );
}

// ---------- chrono ----------

function Chrono({
  incident,
  lecture,
  vue,
  maintenant,
}: {
  incident: Incident;
  lecture: LectureAgent;
  vue: EtatVue;
  maintenant: number;
}) {
  const premiere =
    incident.temps_session?.premiere_vue ??
    [...(incident.evenements ?? [])].map((e) => e.horodatage).filter(Boolean).sort()[0] ??
    [...(incident.chaine ?? [])].map((m) => m.horodatage).filter(Boolean).sort()[0];
  const tDebut = ms(premiere);
  const tDetect = ms(lecture.detection ?? incident.temps_session?.detecte_a);
  const tRemonte = ms(incident.ouvert_le);
  const premiereDecision = [...(incident.decisions ?? [])].sort((a, b) => (a.horodatage ?? "").localeCompare(b.horodatage ?? ""))[0];
  const tDecision = ms(premiereDecision?.horodatage);
  const enAttente = vue === "attente" && !premiereDecision;

  // Refus d'office : la décision, c'est le refus. Rien à attendre, pas de compteur.
  const decision = lecture.refus
    ? {
        lib: "Refusé par Dédale en",
        val: dureeCourte(lecture.refus.delai),
        sous: "sans attendre personne",
        vivant: false,
      }
    : premiereDecision
      ? { lib: "Décision", val: duree(tDecision - tRemonte), sous: "après le signalement", vivant: false }
      : enAttente
        ? { lib: "Décision", val: duree(maintenant - tRemonte), sous: "en attente, le compteur tourne", vivant: true }
        : { lib: "Décision", val: "—", sous: "aucune décision notée", vivant: false };

  const etapes = [
    { lib: "Repéré", val: duree(tDetect - tDebut), sous: "après sa première action", vivant: false },
    { lib: "Signalé au SOC", val: duree(Math.max(0, tRemonte - tDetect)), sous: "après le repérage", vivant: false },
    decision,
  ];
  return (
    <div className="ag-chrono" role="group" aria-label="Temps de réaction">
      {etapes.map((e) => (
        <div key={e.lib} className={`ag-chrono-etape ${e.vivant ? "vivant" : ""}`}>
          <span className="ag-chrono-lib">{e.lib}</span>
          <span className="ag-chrono-val">{e.val}</span>
          <span className="ag-chrono-sous">{e.sous}</span>
        </div>
      ))}
    </div>
  );
}

// ---------- boîte noire ----------

const VOIR: Record<string, string> = {
  mail: "Voir le mail en entier",
  document: "Voir le document en entier",
  outil: "Voir la description de l'outil",
};

// Frise d'étapes dépliables, commune aux agents et aux salariés : une ligne
// de points colorés, puis une étape par ligne. Toute la ligne se déplie au
// clic, et plusieurs étapes peuvent rester ouvertes pour comparer.
export function FriseEtapes({
  maillons,
  sourcil,
  titre,
  idTitre,
  droite,
  avant,
  maintenant,
  voir,
  ouvrirSource,
}: {
  maillons: MaillonAgent[];
  sourcil: string;
  titre: string;
  idTitre: string;
  droite?: ReactNode;
  avant?: ReactNode;
  maintenant: number;
  voir?: string;
  ouvrirSource?: () => void;
}) {
  const n = maillons.length;
  const [ouverts, setOuverts] = useState<Set<string>>(() => new Set());
  const basculer = (id: string) =>
    setOuverts((s) => {
      const c = new Set(s);
      if (c.has(id)) c.delete(id);
      else c.add(id);
      return c;
    });
  return (
    <section className="ag-coque ag-zone-chaine" aria-labelledby={idTitre}>
      <div className="ag-noyau">
        <header className="ag-carte-tete">
          <div>
            <span className="ag-sourcil">{sourcil}</span>
            <h3 id={idTitre}>{titre}</h3>
          </div>
          {droite}
        </header>
        {avant}
        {/* Au-delà de huit étapes, la ligne de points ne se lit plus : la liste suffit. */}
        {n <= 8 && (
          <ol className="ag-fil" aria-hidden="true" style={{ gridTemplateColumns: `repeat(${n}, minmax(0, 1fr))` }}>
            {maillons.map((m) => (
              <li key={m.id} className={`ton-${m.ton}`}>
                <span className="ag-fil-point" />
                <span className="ag-fil-lib">{m.lib}</span>
              </li>
            ))}
          </ol>
        )}
        <ol className="ag-maillons">
          {maillons.map((m, i) => (
            <Maillon
              key={m.id}
              m={m}
              i={i}
              maintenant={maintenant}
              ouvert={ouverts.has(m.id)}
              basculer={() => basculer(m.id)}
              voir={m.cliquable && ouvrirSource ? voir : undefined}
              ouvrirSource={m.cliquable ? ouvrirSource : undefined}
            />
          ))}
        </ol>
      </div>
    </section>
  );
}

function Maillon({
  m,
  i,
  maintenant,
  ouvert,
  basculer,
  voir,
  ouvrirSource,
}: {
  m: MaillonAgent;
  i: number;
  maintenant: number;
  ouvert: boolean;
  basculer: () => void;
  voir?: string;
  ouvrirSource?: () => void;
}) {
  const idDetail = `etape-${m.id}`;
  return (
    <li className={`ag-maillon ton-${m.ton} ${ouvert ? "deplie" : ""}`} style={{ ["--i" as string]: i }}>
      {/* Le picto ouvre aussi l'étape : toute la ligne répond au clic. */}
      <div className="ag-rail" onClick={basculer} aria-hidden="true">
        <span className="ag-noeud">
          <Icone nom={(m.icone ?? m.cle) as NomIcone} taille={17} />
        </span>
      </div>
      <div className="ag-maillon-corps">
        <button type="button" className="ag-etape-btn" aria-expanded={ouvert} aria-controls={idDetail} onClick={basculer}>
          <span className="ag-maillon-tete">
            <span className="ag-lib">{m.lib}</span>
            <Heure iso={m.horodatage} />
            <span className="ag-chevron" aria-hidden="true" />
          </span>
          <span className="ag-maillon-titre">{m.titre}</span>
          {m.texte && (
            <span className="ag-maillon-texte">
              <TexteCanary texte={m.texte} />
            </span>
          )}
          {m.enCours && m.horodatage && (
            <span className="ag-attente">
              <span className="ag-etat-point" /> en attente depuis {duree(maintenant - ms(m.horodatage))}
            </span>
          )}
        </button>
        {voir && ouvrirSource && (
          <button type="button" className="ag-voir" onClick={ouvrirSource}>
            <Icone nom="oeil" taille={15} />
            {voir}
          </button>
        )}
        <Depliant ouvert={ouvert} id={idDetail}>
          <DetailEtape detail={m.detail} horodatage={m.horodatage} />
        </Depliant>
      </div>
    </li>
  );
}

// ---------- décision ----------

const JOURNAL: Record<string, string> = {
  couper: "a coupé l'agent",
  valider_riposte: "a coupé l'agent",
  reprendre: "a laissé passer l'action",
  ignorer: "a classé l'alerte sans suite",
  clore: "a clos l'incident",
};

const ETAT_LONG: Record<EtatVue, string> = {
  attente: "L'action est retenue, elle attend votre décision",
  refusee: "Action refusée, rien n'est parti",
  coupee: "Agent arrêté, rien n'est sorti",
  reprise: "Action laissée passer une fois, agent surveillé",
  close: "Incident clos",
  classee: "Classé sans suite",
  surveillee: "Agent en service, surveillé",
};

type Lourde = "couper" | "reprendre";

const PREAVIS: Record<Lourde, string> = {
  couper: "Coupure de l'agent",
  reprendre: "L'action part",
};

function PanneauDecision({
  incident,
  lecture,
  vue,
  maintenant,
  conseil,
  droitSuggere,
  decisionEnCours,
  erreurDecision,
  trancher,
}: {
  incident: Incident;
  lecture: LectureAgent;
  vue: EtatVue;
  maintenant: number;
  conseil: string | null;
  droitSuggere: string | null;
  decisionEnCours: DecisionAction | null;
  erreurDecision: string | null;
  trancher: (a: DecisionAction, motif?: string) => void;
}) {
  const { retirerDroit, sessions } = useDonnees();
  const analyste = useAnalyste();
  const [confirmation, setConfirmation] = useState<DecisionAction | null>(null);
  const [retrait, setRetrait] = useState<{ enCours: boolean; erreur: string | null; fait: string | null }>({
    enCours: false,
    erreur: null,
    fait: null,
  });
  const differee = useDifferee<Lourde>((action, motif) => trancher(action, motif), incident.id);
  useEffect(() => setConfirmation(null), [incident.id, lecture.issue]);
  useEffect(() => setRetrait({ enCours: false, erreur: null, fait: null }), [incident.id]);

  const agent = nomAgent(sessions.find((s) => s.id === incident.session_id)?.agent);
  const ferme = incident.statut === "clos" || incident.statut === "ignore";
  const occupe = decisionEnCours !== null || retrait.enCours || differee.attente !== null;
  // Incident critique, ou téléphone : Couper et Laisser passer demandent une
  // confirmation avec un motif, puis laissent cinq secondes pour annuler.
  const critique = incident.gravite === "critique";
  const garde = critique || estPetitEcran();
  const peutCouper = !occupe && lecture.issue !== "coupee" && !ferme;
  const peutReprendre = !occupe && lecture.appelLiberable;
  // Désarmé avant lecture : rien à laisser passer, l'agent attend d'être relancé.
  const relancer = lecture.prevenu && !lecture.appel && incident.etat === "suspendue" && !ferme;
  // Clore : après un refus d'office, ou pour une alerte qui n'a pas arrêté l'agent.
  const alerteALire = !ferme && incident.etat === "active" && (!incident.statut || incident.statut === "ouvert");
  const proposerClore = Boolean(lecture.refus) || alerteALire;
  const peutClore = !occupe && (vue === "refusee" || alerteALire);
  // « Couper » n'est l'action principale, rouge plein, que si un appel attend.
  const couperPrincipal = vue === "attente" && !(lecture.prevenu && !lecture.appel);
  const dejaPasse = (incident.decisions ?? []).some((d) => d.action === "reprendre");

  // Droit à retirer : celui que conseille le copilote, sinon celui que l'action
  // retenue exigeait, sinon le premier droit en trop.
  const retirables = incident.droits_retirables ?? [];
  const droit =
    [droitSuggere, lecture.appel?.scope, retirables[0]?.code]
      .filter((c): c is string => Boolean(c))
      .map((c) => retirables.find((r) => r.code === c))
      .find(Boolean) ?? null;
  const peutRetirer = !occupe && droit !== null;

  const conseilCouper = couperPrincipal && (conseil === "couper" || conseil === "valider_riposte");
  const conseilReprendre = conseil === "reprendre";
  const conseilClore = conseil === "clore";

  const aideCouper =
    lecture.issue === "coupee"
      ? "Déjà fait : l'agent est arrêté."
      : ferme
        ? "Le dossier est fermé."
        : vue === "refusee"
          ? "Pour arrêter aussi sa session : toute action suivante sera refusée."
          : vue === "attente" && lecture.appel
            ? "L'action retenue n'a pas lieu et l'agent perd ses accès."
            : "L'agent perd ses accès : toute action suivante sera refusée.";
  const aideReprendre = lecture.appelLiberable
    ? "Seule cette action passe, une fois. L'agent reste surveillé."
    : lecture.issue === "coupee"
      ? "L'agent est arrêté : plus rien à laisser passer."
      : lecture.issue === "reprise"
        ? "Déjà fait : l'action est passée."
        : lecture.refus
          ? "Dédale a déjà refusé cette action."
          : "Aucune action n'attend de décision.";
  const aideRetirer = retrait.fait
    ? `Fait : l'agent ne peut plus ${retrait.fait}.`
    : droit
      ? `L'agent ne pourra plus ${libelleDroit(droit.code, droit.libelle)}. Le reste de son travail continue.`
      : "Aucun accès en trop à retirer pour cet agent.";
  const aideClore = alerteALire
    ? "Vous avez lu l'alerte : le dossier se ferme, l'agent continue son travail."
    : vue === "refusee"
      ? "L'action est déjà refusée : le dossier se ferme."
      : "Déjà fait : le dossier est clos.";

  // Couper et Laisser passer : confirmation quand il le faut, sinon envoi direct.
  const demander = (action: DecisionAction) => {
    if (occupe) return;
    const lourde = action === "couper" || action === "reprendre";
    if ((lourde && garde) || action === "reprendre" || !analyste) {
      setConfirmation(action);
      return;
    }
    trancher(action);
  };
  const confirmer = (motif: string) => {
    const action = confirmation;
    setConfirmation(null);
    if (!action) return;
    if ((action === "couper" || action === "reprendre") && garde) differee.lancer(action, motif);
    else trancher(action, motif || undefined);
  };

  const cliquerRetirer = async () => {
    if (!droit || !peutRetirer) return;
    setRetrait({ enCours: true, erreur: null, fait: null });
    try {
      await retirerDroit(incident.id, droit.code, analyste || "analyste");
      setRetrait({ enCours: false, erreur: null, fait: libelleDroit(droit.code, droit.libelle) });
    } catch (e) {
      setRetrait({ enCours: false, erreur: e instanceof Error ? e.message : "Le retrait n'a pas pu être envoyé.", fait: null });
    }
  };

  const etatLong =
    vue === "coupee" && dejaPasse
      ? "Agent arrêté, une action était passée avant"
      : relancer
        ? "L'agent est en pause, il attend votre décision"
        : ETAT_LONG[vue];
  // Sous le titre : le compteur s'il y a une attente, la durée du refus sinon.
  const sousTitre =
    vue === "attente" && lecture.detection
      ? `depuis ${duree(maintenant - ms(lecture.detection))}`
      : lecture.refus && (vue === "refusee" || vue === "close")
        ? `Refusé par Dédale en ${dureeCourte(lecture.refus.delai)}, sans attendre personne.`
        : null;
  const enJeu = vue === "attente" ? lecture.enJeu : lecture.enJeu.replace(/^L'agent veut /, "L'agent voulait ");

  // Journal : décisions (avec leur motif), retraits de droits, dans l'ordre.
  const motifs = (incident.journal_console ?? []).filter((j) => j.acte === "decision" && j.motif);
  const journal = [
    ...(incident.decisions ?? []).map((d) => {
      const m = motifs.find((j) => j.action === d.action && (j.horodatage ?? "") >= (d.horodatage ?? ""));
      return { h: d.horodatage, qui: d.analyste, quoi: JOURNAL[d.action] ?? d.action, motif: m?.motif };
    }),
    ...(incident.correctifs ?? []).map((c) => ({
      h: c.horodatage,
      qui: c.analyste ?? "l'analyste",
      quoi: `a retiré l'accès « ${libelleDroit(c.code, c.libelle)} »`,
      motif: undefined as string | undefined,
    })),
  ].sort((a, b) => (a.h ?? "").localeCompare(b.h ?? ""));

  const boutonClore = proposerClore ? (
    <div className="ag-action" key="clore">
      <button
        type="button"
        className={`ag-pilule ${peutClore ? "ag-pilule-clore" : "ag-pilule-reprendre"}`}
        disabled={!peutClore}
        onClick={() => demander("clore")}
      >
        <span>
          {decisionEnCours === "clore" ? "Clôture…" : "Clore l'incident"}
          {conseilClore && peutClore && <span className="ag-conseil">conseillé</span>}
        </span>
        <span className="ag-rond">
          <Icone nom="decision" taille={15} />
        </span>
      </button>
      <p className="ag-aide">{aideClore}</p>
    </div>
  ) : null;

  const boutonCouper = (
    <div className="ag-action" key="couper">
      <button
        type="button"
        className={`ag-pilule ${couperPrincipal ? "ag-pilule-couper" : "ag-pilule-couper-second"}`}
        disabled={!peutCouper}
        onClick={() => demander("couper")}
      >
        <span>
          {decisionEnCours === "couper" ? "Coupure…" : "Couper l'agent"}
          {conseilCouper && peutCouper && <span className="ag-conseil">conseillé</span>}
        </span>
        <span className="ag-rond">
          <Icone nom="couper" taille={15} />
        </span>
      </button>
      <p className="ag-aide">{aideCouper}</p>
    </div>
  );

  const boutonRelancer = relancer ? (
    <div className="ag-action" key="relancer">
      <button
        type="button"
        className="ag-pilule ag-pilule-clore"
        disabled={occupe}
        onClick={() => (analyste ? trancher("reprendre") : setConfirmation("reprendre"))}
      >
        <span>
          {decisionEnCours === "reprendre" ? "Envoi…" : "Remettre l'agent en service"}
          {conseilReprendre && <span className="ag-conseil">conseillé</span>}
        </span>
        <span className="ag-rond">
          <Icone nom="reprendre" taille={14} />
        </span>
      </button>
      <p className="ag-aide">Il n'a rien suivi : il reprend son travail, toujours surveillé.</p>
    </div>
  ) : null;

  const boutonReprendre = relancer ? null : (
    <div className="ag-action" key="reprendre">
      <button
        type="button"
        className="ag-pilule ag-pilule-reprendre"
        disabled={!peutReprendre}
        onClick={() => demander("reprendre")}
      >
        <span>
          {decisionEnCours === "reprendre" ? "Envoi…" : "Laisser passer cette action"}
          {conseilReprendre && peutReprendre && <span className="ag-conseil">conseillé</span>}
        </span>
        <span className="ag-rond">
          <Icone nom="reprendre" taille={14} />
        </span>
      </button>
      <p className="ag-aide">{aideReprendre}</p>
    </div>
  );

  const boutonRetirer = (
    <div className="ag-action" key="retirer">
      <button type="button" className="ag-pilule ag-pilule-retirer" disabled={!peutRetirer} onClick={() => void cliquerRetirer()}>
        <span>
          {retrait.enCours ? "Retrait…" : "Retirer ce droit à l'agent"}
          {droitSuggere && droit && droit.code === droitSuggere && peutRetirer && <span className="ag-conseil">conseillé</span>}
        </span>
        <span className="ag-rond">
          <Icone nom="correctif" taille={15} />
        </span>
      </button>
      <p className="ag-aide">{aideRetirer}</p>
    </div>
  );

  const titreConfirmation =
    confirmation === "couper"
      ? `Couper ${agent} ?`
      : confirmation === "reprendre"
        ? relancer
          ? `Remettre ${agent} en service ?`
          : `Laisser passer l'action de ${agent} ?`
        : confirmation === "clore"
          ? "Clore l'incident ?"
          : "";
  const aideConfirmation =
    confirmation === "couper"
      ? "Il perd ses accès tout de suite. Vous aurez cinq secondes pour annuler."
      : confirmation === "reprendre"
        ? relancer
          ? "Il reprend son travail, toujours surveillé."
          : `${lecture.enJeu.replace(/^L'agent veut /, "Elle va ")} Rien d'autre ne passe.`
        : undefined;

  return (
    <section className={`ag-coque ag-zone-decision issue-${vue}`} aria-labelledby="ag-decision-titre">
      <div className="ag-noyau">
        <header className="ag-carte-tete">
          <div>
            <span className="ag-sourcil">Votre décision</span>
            <h3 id="ag-decision-titre" className="ag-etat-long decision-cible" tabIndex={-1} key={vue} aria-live="polite">
              <span className="ag-etat-point" />
              {etatLong}
            </h3>
            {sousTitre && <span className="ag-depuis">{sousTitre}</span>}
          </div>
        </header>

        {lecture.appel && (
          <p className="ag-enjeu">
            <TexteCanary texte={enJeu} />
          </p>
        )}

        {differee.attente ? (
          <BandeauAnnulation texte={PREAVIS[differee.attente.action]} restant={differee.restant} annuler={differee.annuler} />
        ) : confirmation ? (
          <BlocConfirmation
            titre={titreConfirmation}
            aide={aideConfirmation}
            libelle={
              confirmation === "couper"
                ? "Couper l'agent"
                : confirmation === "reprendre"
                  ? relancer
                    ? "Remettre en service"
                    : "Laisser passer"
                  : "Clore"
            }
            danger={confirmation === "couper"}
            motifObligatoire={(confirmation === "couper" || (confirmation === "reprendre" && !relancer)) && garde}
            confirmer={confirmer}
            annuler={() => setConfirmation(null)}
          />
        ) : (
          <div className="ag-actions" aria-busy={occupe}>
            {boutonRelancer}
            {boutonClore}
            {boutonCouper}
            {boutonReprendre}
            {boutonRetirer}
          </div>
        )}

        {erreurDecision && (
          <p className="decision-erreur" role="alert">
            {erreurDecision}
          </p>
        )}
        {retrait.erreur && (
          <p className="decision-erreur" role="alert">
            {retrait.erreur}
          </p>
        )}

        {journal.length > 0 && (
          <ol className="ag-journal" aria-label="Journal des décisions">
            {journal.map((j, i) => (
              <li key={i}>
                <Heure iso={j.h} />
                <span>
                  {j.qui} {j.quoi}
                  {j.motif && <span className="ag-motif"> · « {j.motif} »</span>}
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}
