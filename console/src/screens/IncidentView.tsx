import { useEffect, useMemo, useRef, useState } from "react";
import { useDonnees } from "../api/store";
import type { ChoixSalarie, DecisionAction, Incident, Pilier } from "../types";
import { FriseEtapes, IncidentAgent } from "../agent/IncidentAgent";
import { SyntheseBloc, useSynthese } from "../agent/Synthese";
import { lireGesteSalarie } from "../salarie/lecture";
import { appartientPilier, BadgeChoixSalarie, heure, libelleType, PILIERS, SegmentsPiliers, Spinner } from "../ui/primitives";
import { estATraiter, etatIncident, GRAVITE, phraseSalarie, titreIncident } from "../ui/mots";

const VIDE_PILIER: Record<Pilier, string> = {
  humain: "Aucun incident salarié. Les postes sont calmes.",
  interne: "Aucun incident d'agent IA. Les agents d'Orbis Pay sont calmes.",
};

const ACTIONS_HUMAIN: { action: DecisionAction; lib: string; aide: string; cls: string }[] = [
  { action: "clore", lib: "Clore le dossier", aide: "Vous avez traité le cas : le dossier est fermé.", cls: "primaire" },
  { action: "ignorer", lib: "Classer sans suite", aide: "Fausse alerte : le dossier est fermé sans suite.", cls: "fantome" },
];

// Les plus récents d'abord. L'ordre ne dépend pas de l'état : une ligne qui
// se règle ne saute pas de place avant de disparaître.
function trier(incidents: Incident[]): Incident[] {
  return [...incidents].sort((a, b) => (b.ouvert_le ?? "").localeCompare(a.ouvert_le ?? ""));
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
  const { incidents, getIncident, decider, chargement } = useDonnees();

  const incidentsVue = useMemo(
    () => trier(incidents.filter((i) => appartientPilier(i.source, pilier))),
    [incidents, pilier]
  );
  const comptes = useMemo(() => {
    const c = { humain: 0, interne: 0 } as Record<Pilier, number>;
    for (const p of PILIERS) c[p.id] = incidents.filter((i) => appartientPilier(i.source, p.id)).length;
    return c;
  }, [incidents]);

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

  // Le flux et le rafraîchissement mettent la liste à jour (décision, action
  // libérée, droit retiré). Quand l'incident courant change, on relit son détail.
  const versionListe = useMemo(() => {
    const i = incidents.find((x) => x.id === idCourant);
    return i
      ? `${i.etat}|${i.statut}|${i.chaine?.length ?? 0}|${i.decisions?.length ?? 0}|${i.correctifs?.length ?? 0}|${i.droits_retirables?.length ?? 0}`
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

  const trancher = async (action: DecisionAction) => {
    if (!idCourant || decisionEnCours) return;
    setDecisionEnCours(action);
    setErreurDecision(null);
    try {
      const resultat = await decider(idCourant, action, "analyste-soc");
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

  const segments = <SegmentsPiliers pilier={pilier} setPilier={setPilier} comptes={comptes} />;

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
      <ListeIncidents key={pilier} incidents={incidentsVue} courant={idCourant} choisir={setIncidentSel} />

      {erreurDetail && <div className="decision-erreur" role="alert">{erreurDetail}</div>}
      {!idCourant ? null : !detail || detail.id !== idCourant ? (
        <Spinner />
      ) : estIncidentAgent(detail) ? (
        <IncidentAgent
          incident={detail}
          majEnCours={chargeDetail}
          decisionEnCours={decisionEnCours}
          erreurDecision={erreurDecision}
          trancher={(a) => void trancher(a)}
        />
      ) : (
        <IncidentSalarie
          incident={detail}
          decisionEnCours={decisionEnCours}
          erreurDecision={erreurDecision}
          trancher={(a) => void trancher(a)}
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
  const [sortants, setSortants] = useState<Record<string, "barre" | "repli">>({});
  const [voirRegles, setVoirRegles] = useState(false);
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

  const affiches = incidents.filter((i) => estATraiter(i) || sortants[i.id]);
  const regles = incidents.filter((i) => !estATraiter(i) && !sortants[i.id]);

  return (
    <section className="panneau liste-inc" aria-labelledby="liste-inc-titre">
      <div className="titre">
        <span id="liste-inc-titre" aria-live="polite">
          {aTraiter.length === 0
            ? "Rien à traiter"
            : `${aTraiter.length} incident${aTraiter.length > 1 ? "s" : ""} à traiter`}
        </span>
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
      </div>
      {affiches.length > 0 && (
        <ul className="liste-inc-lignes">
          {affiches.map((i) => (
            <LigneIncident
              key={i.id}
              i={i}
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
            <LigneIncident key={i.id} i={i} actif={i.id === courant} choisir={choisir} discret />
          ))}
        </ul>
      )}
    </section>
  );
}

function LigneIncident({
  i,
  actif,
  sortie,
  discret,
  choisir,
}: {
  i: Incident;
  actif: boolean;
  sortie?: "barre" | "repli";
  discret?: boolean;
  choisir: (id: string) => void;
}) {
  const e = etatIncident(i);
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
          <span className={`inc-point e-${e.cls}`} aria-hidden="true" />
          <span className="inc-titre">{titreIncident(i)}</span>
          <span className="inc-heure">{heure(i.ouvert_le).slice(0, 5)}</span>
          <span className={`inc-etat e-${e.cls}`}>{e.lib}</span>
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
  const evenement = [...(inc.evenements ?? [])].reverse().find((e) => e.type === "avertissement");
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

function IncidentSalarie({
  incident,
  decisionEnCours,
  erreurDecision,
  trancher,
}: {
  incident: Incident;
  decisionEnCours: DecisionAction | null;
  erreurDecision: string | null;
  trancher: (a: DecisionAction) => void;
}) {
  const { synthese, prete } = useSynthese(incident);
  const choix = choixDe(incident);
  const lecture = useMemo(() => lireGesteSalarie(incident), [incident]);
  const etat = etatIncident(incident);
  const ferme = incident.statut === "clos" || incident.statut === "ignore";

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
          <div className="geste-lib">Le message affiché par Dédale</div>
          <div className="sal-message">
            {lecture.message.titre && <span className="sal-message-titre">{lecture.message.titre}</span>}
            {lecture.message.explication && <span className="sal-message-texte">{lecture.message.explication}</span>}
            {lecture.message.lien && <span className="sal-message-lien">{lecture.message.lien}</span>}
          </div>
        </div>
      )}
    </div>
  );

  return (
    <div className="ag-dossier">
      <section className="ag-coque ag-entete" aria-labelledby="sal-titre">
        <div className="ag-noyau">
          <div className="ag-entete-haut">
            <span className={`gravite ${incident.gravite}`}>{GRAVITE[incident.gravite] ?? incident.gravite}</span>
            <span className={`inc-etat e-${etat.cls}`}>{etat.lib}</span>
            <span className="ag-meta">
              {libelleType(incident.type)} · signalé à {heure(incident.ouvert_le).slice(0, 5)}
            </span>
          </div>
          <h2 id="sal-titre" className="ag-titre">{titreIncident(incident)}</h2>
          <SyntheseBloc synthese={synthese} prete={prete} repli={[phraseSalarie(incident.type, choix)]} />
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
          className={`ag-coque ag-zone-decision issue-salarie ${ferme ? "issue-salarie-clos" : "issue-salarie-attente"}`}
          aria-labelledby="sal-decision-titre"
        >
          <div className="ag-noyau">
            <header className="ag-carte-tete">
              <div>
                <span className="ag-sourcil">Votre décision</span>
                <h3 id="sal-decision-titre" className="ag-etat-long">
                  <span className="ag-etat-point" />
                  {ferme ? (incident.statut === "ignore" ? "Classé sans suite" : "Dossier clos") : "Le dossier attend votre décision"}
                </h3>
              </div>
            </header>
            <p className="ag-enjeu">Dédale ne bloque jamais le poste : il prévient le salarié, puis vous décidez de la suite.</p>
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
            {erreurDecision && (
              <p className="decision-erreur" role="alert">
                {erreurDecision}
              </p>
            )}
            {incident.decisions?.length > 0 && (
              <ol className="ag-journal" aria-label="Journal des décisions">
                {incident.decisions.map((d, i) => (
                  <li key={i}>
                    <span className="ag-heure">{heure(d.horodatage)}</span>
                    <span>
                      {d.analyste} {d.action === "ignorer" ? "a classé sans suite" : "a clos le dossier"}
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
