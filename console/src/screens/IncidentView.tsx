import { useEffect, useMemo, useRef, useState } from "react";
import { useDonnees } from "../api/store";
import type { ActionRemediation, ChoixSalarie, DecisionAction, Incident, Pilier, RevelationIdentite } from "../types";
import { FriseEtapes, IncidentAgent } from "../agent/IncidentAgent";
import { SyntheseBloc, useSynthese } from "../agent/Synthese";
import { BadgeIntegrite, MenuExport } from "../agent/OutilsDossier";
import { AvisRelecteur } from "../agent/PreTri";
import { Icone } from "../agent/icones";
import { desarmer } from "../agent/preuve";
import { lireGesteSalarie } from "../salarie/lecture";
import { useAnalyste } from "../ui/analyste";
import { BlocConfirmation } from "../ui/Confirmation";
import { BandeauConfidentialite } from "../ui/Confidentialite";
import { compter } from "../ui/compteurs";
import { appartientPilier, BadgeChoixSalarie, heure, libelleType, SegmentsPiliers, Spinner } from "../ui/primitives";
import { attendDecision, estATraiter, etatIncident, GRAVITE, phraseSalarie, quiIncident, titreIncident } from "../ui/mots";

const VIDE_PILIER: Record<Pilier, string> = {
  humain: "Aucun dossier salarié. Les postes sont calmes.",
  interne: "Aucun incident d'agent IA. Les agents d'Orbis Pay sont calmes.",
};

// Décision attendue d'abord, puis le reste à traiter, puis le plus récent. Une
// ligne qui se règle reste à sa place le temps de se barrer, puis part dans
// « réglés ».
function rang(i: Incident): number {
  if (attendDecision(i)) return 0;
  if (estATraiter(i)) return 1;
  return 2;
}
function trier(incidents: Incident[]): Incident[] {
  return [...incidents].sort((a, b) => rang(a) - rang(b) || (b.ouvert_le ?? "").localeCompare(a.ouvert_le ?? ""));
}

// Donne le focus au panneau de décision : un Tab de plus et on est sur le
// premier bouton. Sans défilement, pour ne pas faire sauter la page.
function focaliserDecision() {
  const cible = document.querySelector<HTMLElement>(".decision-cible");
  cible?.focus({ preventScroll: true });
}

export function IncidentView({
  incidentSel,
  setIncidentSel,
  pilier,
  setPilier,
}: {
  incidentSel: string | null;
  setIncidentSel: (id: string) => void;
  pilier: Pilier;
  setPilier: (p: Pilier) => void;
}) {
  const { incidents, sessions, inventaire, activite, getIncident, decider, chargement } = useDonnees();
  const analyste = useAnalyste();

  const incidentsVue = useMemo(
    () => trier(incidents.filter((i) => appartientPilier(i.source, pilier))),
    [incidents, pilier]
  );
  const comptes = useMemo(() => compter(incidents, sessions, inventaire, activite), [incidents, sessions, inventaire, activite]);

  // Par défaut, le premier incident à traiter. Le choix est aussitôt fixé :
  // un incident qui se règle reste affiché jusqu'à ce qu'on en ouvre un autre.
  const parDefaut = incidentsVue.find(estATraiter)?.id ?? null;
  const idCourant = useMemo(() => {
    if (incidentSel) return incidentsVue.some((i) => i.id === incidentSel) ? incidentSel : null;
    return parDefaut;
  }, [incidentSel, incidentsVue, parDefaut]);
  useEffect(() => {
    if (!incidentSel && parDefaut) setIncidentSel(parDefaut);
  }, [incidentSel, parDefaut, setIncidentSel]);

  const [detail, setDetail] = useState<Incident | null>(null);
  const [chargeDetail, setChargeDetail] = useState(false);
  const [erreurDetail, setErreurDetail] = useState<string | null>(null);
  const [decisionEnCours, setDecisionEnCours] = useState<DecisionAction | null>(null);
  const [erreurDecision, setErreurDecision] = useState<string | null>(null);
  const focusApres = useRef(false);

  useEffect(() => {
    if (!idCourant) {
      setDetail(null);
      return;
    }
    let vivant = true;
    // On part de la version de la liste, puis on récupère le détail à jour.
    setDetail(incidents.find((i) => i.id === idCourant) ?? null);
    setErreurDetail(null);
    setErreurDecision(null);
    setChargeDetail(true);
    getIncident(idCourant)
      .then((d) => vivant && setDetail(d))
      .catch(() => vivant && setErreurDetail("Le détail n'a pas pu être actualisé. Dernières données disponibles affichées."))
      .finally(() => vivant && setChargeDetail(false));
    return () => {
      vivant = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idCourant, getIncident]);

  // Après un choix dans la liste, le focus va au panneau de décision.
  useEffect(() => {
    if (!focusApres.current || !detail || detail.id !== idCourant) return;
    focusApres.current = false;
    window.requestAnimationFrame(focaliserDecision);
  }, [detail, idCourant]);

  // Raccourci « d » : aller à la décision, depuis n'importe où sur l'écran.
  useEffect(() => {
    const touche = (e: KeyboardEvent) => {
      const cible = e.target as HTMLElement | null;
      if (e.key !== "d" || e.metaKey || e.ctrlKey || e.altKey) return;
      if (cible && (cible.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(cible.tagName))) return;
      e.preventDefault();
      focaliserDecision();
    };
    document.addEventListener("keydown", touche);
    return () => document.removeEventListener("keydown", touche);
  }, []);

  // Le flux et le rafraîchissement mettent la liste à jour (décision, action
  // libérée, droit retiré). Quand l'incident courant change, on relit son détail.
  const versionListe = useMemo(() => {
    const i = incidents.find((x) => x.id === idCourant);
    return i
      ? `${i.etat}|${i.statut}|${i.chaine?.length ?? 0}|${i.decisions?.length ?? 0}|${i.correctifs?.length ?? 0}|${i.droits_retirables?.length ?? 0}|${i.journal_console?.length ?? 0}`
      : "";
  }, [incidents, idCourant]);
  const versionVue = useRef("");
  useEffect(() => {
    if (!idCourant || !versionListe) return;
    const precedente = versionVue.current;
    versionVue.current = `${idCourant}#${versionListe}`;
    if (!precedente.startsWith(`${idCourant}#`) || precedente === versionVue.current) return;
    let vivant = true;
    getIncident(idCourant)
      .then((d) => vivant && setDetail(d))
      .catch(() => undefined);
    return () => {
      vivant = false;
    };
  }, [idCourant, versionListe, getIncident]);

  const choisir = (id: string) => {
    focusApres.current = true;
    setIncidentSel(id);
  };

  const trancher = async (action: DecisionAction, motif?: string) => {
    if (!idCourant || decisionEnCours) return;
    setDecisionEnCours(action);
    setErreurDecision(null);
    try {
      const resultat = await decider(idCourant, action, analyste || "analyste", motif);
      setDetail(resultat);
      try {
        setDetail(await getIncident(idCourant));
      } catch {
        // La réponse de décision contient déjà le nouvel état.
      }
    } catch (e) {
      setErreurDecision(e instanceof Error ? e.message : "La décision n'a pas pu être envoyée.");
      try {
        setDetail(await getIncident(idCourant));
      } catch {
        // État incertain : le message reste visible et aucun succès n'est supposé.
      }
    } finally {
      setDecisionEnCours(null);
    }
  };

  if (chargement) return <Spinner />;

  const segments = <SegmentsPiliers pilier={pilier} setPilier={setPilier} comptes={comptes.aTraiter} />;

  if (incidentSel && !idCourant)
    return (
      <>
        {segments}
        {incidents.some((i) => i.id === incidentSel) ? (
          <Spinner texte="Ouverture de l'incident…" />
        ) : (
          <div className="vide" role="status">Cet incident n'est plus dans la liste.</div>
        )}
      </>
    );

  if (incidentsVue.length === 0)
    return (
      <>
        {segments}
        <div className="vide">{VIDE_PILIER[pilier]}</div>
      </>
    );

  return (
    <>
      {segments}
      <ListeIncidents key={pilier} incidents={incidentsVue} courant={idCourant} choisir={choisir} />

      {erreurDetail && <div className="decision-erreur" role="alert">{erreurDetail}</div>}
      {detail && detail.id === idCourant && <BandeauConfidentialite incident={detail} />}
      {!idCourant ? null : !detail || detail.id !== idCourant ? (
        <Spinner />
      ) : estIncidentAgent(detail) ? (
        <IncidentAgent
          incident={detail}
          majEnCours={chargeDetail}
          decisionEnCours={decisionEnCours}
          erreurDecision={erreurDecision}
          trancher={(a, m) => void trancher(a, m)}
        />
      ) : (
        <IncidentSalarie
          incident={detail}
          decisionEnCours={decisionEnCours}
          erreurDecision={erreurDecision}
          trancher={(a, m) => void trancher(a, m)}
        />
      )}
    </>
  );
}

// ---------- liste des incidents ----------

// Durées du départ d'une ligne réglée : barrée, puis repliée.
const BARRE_MS = 3600;
const REPLI_MS = 450;

// La liste ne montre que ce qui reste à traiter. Une ligne qui vient d'être
// réglée se barre quelques secondes, puis se replie et disparaît. Les
// incidents déjà réglés se rangent sous « réglés (n) ».
function ListeIncidents({
  incidents,
  courant,
  choisir,
}: {
  incidents: Incident[];
  courant: string | null;
  choisir: (id: string) => void;
}) {
  const { sessions, aRegarder } = useDonnees();
  const [sortants, setSortants] = useState<Record<string, "barre" | "repli">>({});
  const [voirRegles, setVoirRegles] = useState(false);
  // File « à regarder » du relecteur IA : priorité haute ou avis incertain.
  const [filtre, setFiltre] = useState(false);
  const fileIci = incidents.filter((i) => aRegarder.includes(i.id) && estATraiter(i));
  const filtreActif = filtre && fileIci.length > 0;
  const precedents = useRef<Set<string> | null>(null);
  const minuteurs = useRef<ReturnType<typeof setTimeout>[]>([]);
  useEffect(() => () => minuteurs.current.forEach(clearTimeout), []);

  const aTraiter = incidents.filter(estATraiter);
  const cleATraiter = aTraiter.map((i) => i.id).join("|");

  useEffect(() => {
    const actuels = new Set(aTraiter.map((i) => i.id));
    const avant = precedents.current;
    precedents.current = actuels;
    if (!avant) return; // premier rendu : rien ne part
    const partis = [...avant].filter((id) => !actuels.has(id) && incidents.some((i) => i.id === id));
    if (partis.length === 0) return;
    setSortants((s) => {
      const c = { ...s };
      for (const id of partis) c[id] = "barre";
      return c;
    });
    for (const id of partis) {
      minuteurs.current.push(
        setTimeout(() => setSortants((s) => (s[id] ? { ...s, [id]: "repli" } : s)), BARRE_MS),
        setTimeout(
          () =>
            setSortants((s) => {
              const c = { ...s };
              delete c[id];
              return c;
            }),
          BARRE_MS + REPLI_MS
        )
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cleATraiter]);

  const affiches = incidents.filter(
    (i) => (estATraiter(i) || sortants[i.id]) && (!filtreActif || aRegarder.includes(i.id))
  );
  const regles = incidents.filter((i) => !estATraiter(i) && !sortants[i.id]);

  return (
    <section className="panneau liste-inc" aria-labelledby="liste-inc-titre">
      <div className="titre">
        <span id="liste-inc-titre" aria-live="polite">
          {aTraiter.length === 0
            ? "Rien à traiter"
            : `${aTraiter.length} incident${aTraiter.length > 1 ? "s" : ""} à traiter`}
        </span>
        <span className="liste-filtres">
          {fileIci.length > 0 && (
            <button
              type="button"
              className={`liste-regles-btn filtre-regarder ${filtreActif ? "actif" : ""}`}
              aria-pressed={filtreActif}
              title="Signalés par le relecteur IA : priorité haute ou avis incertain"
              onClick={() => setFiltre((v) => !v)}
            >
              à regarder ({fileIci.length})
            </button>
          )}
          {regles.length > 0 && (
            <button
              type="button"
              className="liste-regles-btn"
              aria-expanded={voirRegles}
              onClick={() => setVoirRegles((v) => !v)}
            >
              réglés ({regles.length})
            </button>
          )}
        </span>
      </div>
      {affiches.length > 0 && (
        <ul className="liste-inc-lignes">
          {affiches.map((i) => (
            <LigneIncident
              key={i.id}
              i={i}
              qui={quiIncident(i, sessions)}
              actif={i.id === courant}
              sortie={sortants[i.id]}
              choisir={choisir}
            />
          ))}
        </ul>
      )}
      {voirRegles && regles.length > 0 && (
        <ul className="liste-inc-lignes liste-regles" aria-label="Incidents réglés">
          {regles.map((i) => (
            <LigneIncident key={i.id} i={i} qui={quiIncident(i, sessions)} actif={i.id === courant} choisir={choisir} discret />
          ))}
        </ul>
      )}
    </section>
  );
}

function LigneIncident({
  i,
  qui,
  actif,
  sortie,
  discret,
  choisir,
}: {
  i: Incident;
  qui: string;
  actif: boolean;
  sortie?: "barre" | "repli";
  discret?: boolean;
  choisir: (id: string) => void;
}) {
  const e = etatIncident(i);
  // La couleur reste à ce qui demande un geste. Un dossier réglé, ou un refus
  // d'office encore à clore, s'affiche en gris : un vert dans la liste « à
  // traiter » dirait le contraire de sa place.
  const cls = discret || (e.aTraiter && e.cls === "ok") ? "neutre" : e.cls;
  return (
    <li className={`inc-item ${sortie ? `sortie-${sortie}` : ""}`}>
      <div className="inc-item-interieur">
        <button
          type="button"
          className={`inc-ligne ${actif ? "actif" : ""} ${sortie ? "regle" : ""} ${discret ? "discret" : ""}`}
          aria-current={actif ? "true" : undefined}
          onClick={() => choisir(i.id)}
          tabIndex={sortie === "repli" ? -1 : undefined}
        >
          <span className={`inc-point e-${cls}`} aria-hidden="true" />
          <span className="inc-titre">
            <span className="inc-qui">{qui}</span>
            {titreIncident(i)}
          </span>
          <span className="inc-heure">{heure(i.ouvert_le).slice(0, 5)}</span>
          <span className={`inc-etat e-${cls}`}>{e.lib}</span>
        </button>
      </div>
    </li>
  );
}

// ---------- incident salarié ----------

// Agent IA interne : écran dédié. Un incident salarié n'y passe jamais.
function estIncidentAgent(inc: Incident): boolean {
  return !estIncidentHumain(inc) && (inc.source === "interne" || (inc.type ?? "").startsWith("interne_"));
}

function estIncidentHumain(inc: Incident): boolean {
  return inc.source === "humain" || inc.source === "physique" || (inc.type ?? "").startsWith("humain_");
}

// Choix du salarié, lu sur l'incident d'abord, puis dans la chaîne et le journal.
function choixDe(inc: Incident): ChoixSalarie | undefined {
  const chaine = inc.chaine ?? [];
  const averti = [...chaine].reverse().find((x) => x.phase === "avertissement");
  const choixMaillon = [...chaine].reverse().find((x) => x.phase === "choix");
  // Le dossier s'ouvre sur un geste continué : ce choix-là compte, même si le
  // salarié a annulé un autre geste ensuite.
  const avertissements = (inc.evenements ?? []).filter((e) => e.type === "avertissement");
  const evenement =
    avertissements.find((e) => e.details?.choix === "continuer") ?? [...avertissements].reverse()[0];
  const brut = evenement?.details?.choix;
  return (
    inc.choix ??
    averti?.choix ??
    (brut === "continuer" || brut === "annuler" ? brut : undefined) ??
    (choixMaillon?.detail.includes("annul")
      ? "annuler"
      : choixMaillon?.detail.includes("continu") || choixMaillon?.detail.includes("passé outre")
        ? "continuer"
        : undefined)
  );
}

const ACTIONS_HUMAIN: { action: DecisionAction; lib: string; aide: string; cls: string }[] = [
  { action: "clore", lib: "Clore le dossier", aide: "Vous avez traité le cas : le dossier est fermé.", cls: "primaire" },
  { action: "ignorer", lib: "Classer sans suite", aide: "Fausse alerte : le dossier est fermé sans suite.", cls: "fantome" },
];

const JOURNAL_HUMAIN: Record<string, string> = {
  clore: "a clos le dossier",
  ignorer: "a classé le dossier sans suite",
  accorder: "a accordé le geste",
  refuser: "a refusé le geste",
};

const REMEDIATIONS: { action: ActionRemediation; lib: string; aide: string }[] = [
  {
    action: "reinitialiser_mot_de_passe",
    lib: "Réinitialiser son mot de passe",
    aide: "Il en choisira un nouveau à sa prochaine connexion.",
  },
  { action: "fermer_sessions", lib: "Fermer ses sessions", aide: "Il est déconnecté de tous ses appareils." },
  { action: "bloquer_domaine", lib: "Bloquer ce domaine pour tous", aide: "Plus aucun salarié ne pourra l'ouvrir." },
];

// Relecture du geste critique par le relecteur IA (événement `relecture`, scellé).
interface Relecture {
  decision?: string;
  motif?: string;
  tranche_par?: string;
  duree_ms?: number;
  modele?: string;
}

function relectureDe(inc: Incident): Relecture | null {
  const ev = [...(inc.evenements ?? [])]
    .reverse()
    .find((e) => e.type === "relecture" && (e.details as Record<string, unknown>)?.acte === "quatre_yeux");
  if (!ev) return null;
  const d = ev.details as Record<string, unknown>;
  return {
    decision: typeof d.decision === "string" ? d.decision : undefined,
    // Le relecteur écrit un motif pour la SOC et un autre pour le salarié : la console lit le premier.
    motif: typeof d.motif_soc === "string" ? desarmer(d.motif_soc) : typeof d.motif === "string" ? desarmer(d.motif) : undefined,
    tranche_par: typeof d.tranche_par === "string" ? d.tranche_par : undefined,
    duree_ms: typeof d.duree_ms === "number" ? d.duree_ms : undefined,
    modele: typeof d.modele === "string" ? d.modele : undefined,
  };
}

function dureeCourte(ms?: number): string {
  if (ms == null) return "";
  if (ms < 1000) return ` en ${Math.max(1, Math.round(ms))} ms`;
  return ` en ${(ms / 1000).toFixed(1).replace(".", ",")} s`;
}

function phraseRelecture(r: Relecture): string {
  const qui = r.tranche_par && r.tranche_par !== "règles" ? `le relecteur IA (${r.tranche_par})` : "les règles du relecteur";
  const issue = r.decision === "accorde" ? "accordé" : "refusé";
  return `Relu par ${qui}${dureeCourte(r.duree_ms)} : ${issue}.`;
}

function useDelaiRestant(debut?: string, delaiS?: number, actif = true): number | null {
  const [maintenant, setMaintenant] = useState(() => Date.now());
  useEffect(() => {
    if (!actif || !debut || !delaiS) return;
    const t = window.setInterval(() => setMaintenant(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, [actif, debut, delaiS]);
  if (!debut || !delaiS) return null;
  const fin = new Date(debut).getTime() + delaiS * 1000;
  return Math.max(0, Math.round((fin - maintenant) / 1000));
}

function IncidentSalarie({
  incident,
  decisionEnCours,
  erreurDecision,
  trancher,
}: {
  incident: Incident;
  decisionEnCours: DecisionAction | null;
  erreurDecision: string | null;
  trancher: (a: DecisionAction, motif?: string) => void;
}) {
  const { synthese, prete } = useSynthese(incident);
  const choix = choixDe(incident);
  const lecture = useMemo(() => lireGesteSalarie(incident), [incident]);
  const etat = etatIncident(incident);
  const ferme = incident.statut === "clos" || incident.statut === "ignore";
  const q = incident.quatre_yeux;
  const relecture = relectureDe(incident);
  // Geste en attente : personne n'a encore tranché, ni le relecteur ni le poste.
  const quatreYeux = Boolean(q && !q.issue && !relecture && !ferme);
  // Recours : le relecteur (ou le délai) a tranché, l'analyste peut revenir dessus.
  const recours = Boolean(q && !ferme && (relecture || q.issue));
  const restant = useDelaiRestant(q?.horodatage, q?.delai_s, quatreYeux);
  const [confirmation, setConfirmation] = useState<DecisionAction | null>(null);
  useEffect(() => setConfirmation(null), [incident.id]);

  const avant = (
    <div className="sal-avant">
      {lecture.geste && (
        <div className="geste-bloc">
          <div className="geste-lib">Le geste</div>
          <div className="geste-val">{lecture.geste}</div>
        </div>
      )}
      {lecture.message && (
        <div className="geste-bloc">
          <div className="geste-lib">Le message affiché par sAIfe</div>
          <div className="sal-message">
            {lecture.message.titre && <span className="sal-message-titre">{lecture.message.titre}</span>}
            {lecture.message.explication && <span className="sal-message-texte">{lecture.message.explication}</span>}
            {lecture.message.lien && <span className="sal-message-lien">{lecture.message.lien}</span>}
          </div>
        </div>
      )}
    </div>
  );

  const titrePanneau = ferme
    ? etat.lib === "Classé sans suite"
      ? "Classé sans suite"
      : etat.lib === "Geste accordé" || etat.lib === "Geste refusé"
        ? etat.lib
        : "Dossier clos"
    : quatreYeux
      ? "Un geste attend votre accord"
      : recours && relecture
        ? `Geste ${relecture.decision === "accorde" ? "accordé" : "refusé"} par ${
            relecture.tranche_par && relecture.tranche_par !== "règles" ? "le relecteur IA" : "les règles du relecteur"
          }`
        : recours && q?.issue === "expire"
          ? "Délai dépassé, le poste a refusé le geste"
          : "Le dossier attend votre décision";

  return (
    <div className="ag-dossier">
      <section className="ag-coque ag-entete" aria-labelledby="sal-titre">
        <div className="ag-noyau">
          <div className="ag-entete-haut">
            <span className={`gravite ${incident.gravite}`}>{GRAVITE[incident.gravite] ?? incident.gravite}</span>
            <span className={`inc-etat e-${etat.cls}`}>{etat.lib}</span>
            <span className="ag-outils">
              <BadgeIntegrite incident={incident} />
              <MenuExport incident={incident} />
            </span>
          </div>
          <Identite incident={incident} />
          <h2 id="sal-titre" className="ag-titre">{titreIncident(incident)}</h2>
          <SyntheseBloc
            synthese={synthese}
            prete={prete}
            repli={[phraseSalarie(incident.type, choix, incident.contexte_humain)]}
          />
          <p className="ag-meta sal-meta">
            {incident.contexte_humain === "telechargement" ? "Téléchargement" : libelleType(incident.type)} · signalé à{" "}
            {heure(incident.ouvert_le).slice(0, 5)}
          </p>
        </div>
      </section>

      <div className="ag-grille">
        <FriseEtapes
          maillons={lecture.maillons}
          sourcil="Sur le poste"
          titre="Ce que le salarié a vu et fait"
          idTitre="sal-chaine-titre"
          droite={<BadgeChoixSalarie choix={choix} />}
          avant={avant}
          maintenant={0}
        />

        <section
          className={`ag-coque ag-zone-decision issue-salarie ${ferme || (recours && !quatreYeux) ? "issue-salarie-clos" : "issue-salarie-attente"}`}
          aria-labelledby="sal-decision-titre"
        >
          <div className="ag-noyau">
            <header className="ag-carte-tete">
              <div>
                <span className="ag-sourcil">Votre décision</span>
                <h3 id="sal-decision-titre" className="ag-etat-long decision-cible" tabIndex={-1}>
                  <span className="ag-etat-point" />
                  {titrePanneau}
                </h3>
                {quatreYeux && restant != null && (
                  <span className="ag-depuis">
                    {restant > 0
                      ? `Le geste reste suspendu encore ${restant} s sur le poste.`
                      : "Délai dépassé : le poste a refusé le geste de lui-même."}
                  </span>
                )}
              </div>
            </header>
            {/* Le geste déjà relu : son verdict suffit, le pré-tri le répéterait. */}
            {!relecture && <AvisRelecteur incident={incident} />}
            {relecture ? (
              <div className="relecture">
                <p className="relecture-titre">
                  {phraseRelecture(relecture)}
                </p>
                {relecture.motif && <p className="relecture-motif">Motif : {relecture.motif}</p>}
                {!ferme && <p className="relecture-recours">Vous pouvez revenir sur cette décision, avec un motif.</p>}
              </div>
            ) : (
              <p className="ag-enjeu">
                {quatreYeux
                  ? "Le salarié a demandé à continuer un geste critique. Son poste attend votre accord : sans réponse, le geste est refusé."
                  : "sAIfe ne bloque jamais le poste : il prévient le salarié, puis vous décidez de la suite."}
              </p>
            )}

            {confirmation ? (
              <BlocConfirmation
                titre={confirmation === "accorder" ? "Accorder le geste au salarié ?" : "Refuser le geste ?"}
                aide={
                  confirmation === "accorder"
                    ? "Le geste part tel quel depuis son poste. Écrivez pourquoi vous l'accordez."
                    : "Le geste n'a pas lieu. Le salarié en est informé sur son poste."
                }
                libelle={confirmation === "accorder" ? "Accorder" : "Refuser"}
                danger={confirmation === "accorder"}
                motifObligatoire={confirmation === "accorder" || recours}
                confirmer={(motif) => {
                  const a = confirmation;
                  setConfirmation(null);
                  trancher(a, motif || undefined);
                }}
                annuler={() => setConfirmation(null)}
              />
            ) : quatreYeux || recours ? (
              <div className="ag-actions" aria-busy={decisionEnCours !== null}>
                <div className="ag-action">
                  <button
                    type="button"
                    className="ag-pilule ag-pilule-clore"
                    disabled={decisionEnCours !== null || (quatreYeux && restant === 0)}
                    onClick={() => setConfirmation("refuser")}
                  >
                    <span>{decisionEnCours === "refuser" ? "Envoi…" : "Refuser"}</span>
                  </button>
                  <p className="ag-aide">Le geste n'a pas lieu. Le poste reste utilisable.</p>
                </div>
                <div className="ag-action">
                  <button
                    type="button"
                    className="ag-pilule ag-pilule-reprendre"
                    disabled={decisionEnCours !== null || (quatreYeux && restant === 0)}
                    onClick={() => setConfirmation("accorder")}
                  >
                    <span>{decisionEnCours === "accorder" ? "Envoi…" : "Accorder"}</span>
                  </button>
                  <p className="ag-aide">Le geste part, avec votre nom et votre motif au journal.</p>
                </div>
              </div>
            ) : (
              <div className="ag-actions" aria-busy={decisionEnCours !== null}>
                {ACTIONS_HUMAIN.map((a) => (
                  <div className="ag-action" key={a.action}>
                    <button
                      type="button"
                      className={`ag-pilule ${a.cls === "primaire" ? "ag-pilule-clore" : "ag-pilule-reprendre"}`}
                      disabled={decisionEnCours !== null || ferme}
                      onClick={() => trancher(a.action)}
                    >
                      <span>{decisionEnCours === a.action ? "Envoi…" : a.lib}</span>
                    </button>
                    <p className="ag-aide">{a.aide}</p>
                  </div>
                ))}
              </div>
            )}
            {erreurDecision && (
              <p className="decision-erreur" role="alert">
                {erreurDecision}
              </p>
            )}

            <Remediations incident={incident} />
            <JournalSalarie incident={incident} />
          </div>
        </section>
      </div>
    </div>
  );
}

// Pseudonyme du salarié ; le nom ne s'affiche qu'après un motif, noté au journal.
function Identite({ incident }: { incident: Incident }) {
  const { revelerIdentite } = useDonnees();
  const analyste = useAnalyste();
  const [ouvert, setOuvert] = useState(false);
  const [motif, setMotif] = useState("");
  const [revele, setRevele] = useState<RevelationIdentite | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [envoi, setEnvoi] = useState(false);
  const champ = useRef<HTMLInputElement>(null);
  useEffect(() => {
    setOuvert(false);
    setRevele(null);
    setMotif("");
    setErreur(null);
  }, [incident.id]);
  useEffect(() => {
    if (ouvert) champ.current?.focus();
  }, [ouvert]);

  const ident = incident.identite;
  const libelle = ident?.libelle ?? "Salarié";
  const revelations = ident?.revelations ?? [];

  const envoyer = async () => {
    if (motif.trim().length < 5 || envoi) return;
    setEnvoi(true);
    setErreur(null);
    try {
      const r = await revelerIdentite(incident.id, motif.trim(), analyste || "analyste");
      setRevele(r);
      setOuvert(false);
    } catch (e) {
      setErreur(e instanceof Error ? e.message : "L'identité n'a pas pu être révélée.");
    } finally {
      setEnvoi(false);
    }
  };

  return (
    <div className="identite">
      <p className="ag-qui">
        <Icone nom="personne" taille={15} />
        <strong>{libelle}</strong>
        {revele?.nom && (
          <span className="identite-nom">
            {" "}
            · {revele.nom}
            {revele.poste ? ` · poste ${revele.poste}` : ""}
          </span>
        )}
        {!revele && !ouvert && (
          <button type="button" className="lien-incident identite-btn" onClick={() => setOuvert(true)}>
            Révéler l'identité
          </button>
        )}
      </p>
      {revele && <p className="identite-note">{revele.message}</p>}
      {!revele && revelations.length > 0 && (
        <p className="identite-note">
          Identité déjà révélée par {revelations[revelations.length - 1].analyste} à{" "}
          {heure(revelations[revelations.length - 1].horodatage).slice(0, 5)}.
        </p>
      )}
      {ouvert && (
        <form
          className="identite-form"
          onSubmit={(e) => {
            e.preventDefault();
            void envoyer();
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") setOuvert(false);
          }}
        >
          <label htmlFor="identite-motif">Pourquoi avez-vous besoin du nom ? Le motif est noté au journal scellé.</label>
          <div className="identite-ligne">
            <input
              id="identite-motif"
              ref={champ}
              value={motif}
              maxLength={200}
              autoComplete="off"
              placeholder="Ex. : réinitialiser son accès avec lui"
              onChange={(e) => setMotif(e.target.value)}
            />
            <button type="submit" className="regle-btn primaire" disabled={motif.trim().length < 5 || envoi}>
              {envoi ? "Envoi…" : "Révéler"}
            </button>
            <button type="button" className="regle-btn" onClick={() => setOuvert(false)}>
              Annuler
            </button>
          </div>
        </form>
      )}
      {erreur && <p className="decision-erreur" role="alert">{erreur}</p>}
    </div>
  );
}

// Actions sur le compte du salarié ou sur le domaine en cause : simulées dans la
// démo, notées au journal scellé comme de vraies.
function Remediations({ incident }: { incident: Incident }) {
  const { remedier } = useDonnees();
  const analyste = useAnalyste();
  const [enCours, setEnCours] = useState<ActionRemediation | null>(null);
  const [retour, setRetour] = useState<{ action: ActionRemediation; texte: string; erreur?: boolean } | null>(null);
  useEffect(() => setRetour(null), [incident.id]);
  const faites = new Map(
    (incident.journal_console ?? []).filter((j) => j.acte === "remediation").map((j) => [j.action, j])
  );
  if (incident.type === "humain_intrusion_physique") return null;
  // Un mail signalé : le compte du salarié n'est pas en cause, seul le domaine l'est.
  const possibles =
    incident.type === "humain_signalement"
      ? REMEDIATIONS.filter((r) => r.action === "bloquer_domaine")
      : incident.contexte_humain === "telechargement"
        ? REMEDIATIONS.filter((r) => r.action !== "reinitialiser_mot_de_passe")
        : REMEDIATIONS;

  const lancer = async (action: ActionRemediation) => {
    setEnCours(action);
    setRetour(null);
    try {
      const r = await remedier(incident.id, action, analyste || "analyste");
      setRetour({ action, texte: desarmer(r.message) });
    } catch (e) {
      setRetour({ action, texte: e instanceof Error ? e.message : "Action impossible.", erreur: true });
    } finally {
      setEnCours(null);
    }
  };

  return (
    <div className="remediations" aria-label="Agir sur le compte">
      <p className="remediations-titre">Agir sur le compte</p>
      <div className="remediations-boutons">
        {possibles.map((r) => {
          const fait = faites.get(r.action);
          return (
            <button
              key={r.action}
              type="button"
              className={`remediation ${fait ? "fait" : ""}`}
              disabled={Boolean(fait) || enCours !== null}
              onClick={() => void lancer(r.action)}
              title={r.aide}
            >
              {fait ? <Icone nom="decision" taille={14} /> : null}
              {enCours === r.action ? "Envoi…" : r.lib}
            </button>
          );
        })}
      </div>
      {retour && (
        <p className={retour.erreur ? "decision-erreur" : "remediation-retour"} role="status">
          {retour.texte}
        </p>
      )}
      <p className="remediations-note">Actions simulées dans cette démo, notées au journal scellé.</p>
    </div>
  );
}

function JournalSalarie({ incident }: { incident: Incident }) {
  const actes = incident.journal_console ?? [];
  const lignes = [
    ...(incident.decisions ?? []).map((d) => {
      const m = actes.find((j) => j.acte === "decision" && j.action === d.action && (j.horodatage ?? "") >= (d.horodatage ?? ""));
      return { h: d.horodatage, texte: `${d.analyste} ${JOURNAL_HUMAIN[d.action] ?? d.action}`, motif: m?.motif };
    }),
    ...actes
      .filter((j) => j.acte === "reveler_identite")
      .map((j) => ({ h: j.horodatage, texte: `${j.analyste} a révélé l'identité`, motif: j.motif })),
    ...actes
      .filter((j) => j.acte === "remediation")
      .map((j) => ({
        h: j.horodatage,
        texte: `${j.analyste} : ${(REMEDIATIONS.find((r) => r.action === j.action)?.lib ?? "action").toLowerCase()}`,
        motif: undefined as string | undefined,
      })),
  ].sort((a, b) => (a.h ?? "").localeCompare(b.h ?? ""));
  if (lignes.length === 0) return null;
  return (
    <ol className="ag-journal" aria-label="Journal du dossier">
      {lignes.map((l, i) => (
        <li key={i}>
          <span className="ag-heure">{heure(l.h)}</span>
          <span>
            {l.texte}
            {l.motif && <span className="ag-motif"> · « {l.motif} »</span>}
          </span>
        </li>
      ))}
    </ol>
  );
}
