import { useEffect, useMemo, useRef, useState } from "react";
import { useDonnees } from "../api/store";
import type {
  ChoixSalarie,
  DecisionAction,
  DroitsAgent,
  Incident,
  MaillonChaine,
  Pilier,
  Session,
} from "../types";
import { IncidentAgent } from "../agent/IncidentAgent";
import { nomTechnique } from "../agent/references";
import {
  appartientPilier,
  BadgeChoixSalarie,
  BadgeEtat,
  BadgeTypeIncident,
  codeDroit,
  heure,
  libDroit,
  libelleType,
  PILIERS,
  SegmentsPiliers,
  Spinner,
} from "../ui/primitives";

const PHASE_LIB: Record<string, string> = {
  entree: "Entrée",
  consigne: "Consigne lue",
  outil: "Appels d'outils",
  sortie: "Sortie de données",
  riposte: "Riposte",
  contexte: "Contexte",
  action_risquee: "Action risquée",
  avertissement: "Avertissement au salarié",
  choix: "Choix du salarié",
  consequence: "Conséquence",
};

const PHASE_PIC: Record<string, string> = {
  entree: "✉",
  consigne: "!",
  outil: "⚙",
  sortie: "⇲",
  riposte: "⛊",
  contexte: "◉",
  action_risquee: "!",
  avertissement: "⚠",
  choix: "◇",
  consequence: "⇲",
};

const VIDE_PILIER: Record<Pilier, string> = {
  humain: "Aucun geste risqué de salarié en incident. Les postes sont calmes.",
  interne: "Aucun incident interne ouvert. Les agents d'Orbis Pay sont calmes.",
};

const ACTIONS_AGENT: { action: DecisionAction; lib: string; cls: string }[] = [
  { action: "valider_riposte", lib: "Valider la riposte", cls: "primaire" },
  { action: "couper", lib: "Couper l'agent", cls: "danger" },
  { action: "reprendre", lib: "Reprendre l'agent", cls: "fantome" },
  { action: "ignorer", lib: "Ignorer", cls: "fantome" },
];
const ACTIONS_HUMAIN: { action: DecisionAction; lib: string; cls: string }[] = [
  { action: "clore", lib: "Clore le suivi", cls: "primaire" },
  { action: "ignorer", lib: "Ignorer l'alerte", cls: "fantome" },
];

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
  const { incidents, sessions, getIncident, decider, chargement } = useDonnees();

  const incidentsVue = useMemo(
    () => incidents.filter((i) => appartientPilier(i.source, pilier)),
    [incidents, pilier]
  );
  const comptes = useMemo(() => {
    const c = { humain: 0, interne: 0 } as Record<Pilier, number>;
    for (const p of PILIERS)
      c[p.id] = incidents.filter((i) => appartientPilier(i.source, p.id)).length;
    return c;
  }, [incidents]);

  const idCourant = useMemo(() => {
    if (incidentSel)
      return incidentsVue.some((i) => i.id === incidentSel) ? incidentSel : null;
    return incidentsVue[0]?.id ?? null;
  }, [incidentSel, incidentsVue]);

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
    // On part de la version de la liste (souvent complète), puis on récupère le
    // détail à jour.
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

  // Le flux WS et le rafraîchissement périodique mettent la liste à jour (riposte
  // de la passerelle, nouvelle décision, appel libéré). Quand la version de
  // l'incident courant change, on relit son détail sans repasser par le spinner.
  const versionListe = useMemo(() => {
    const i = incidents.find((x) => x.id === idCourant);
    return i ? `${i.etat}|${i.statut}|${i.chaine?.length ?? 0}|${i.decisions?.length ?? 0}` : "";
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

  const segments = (
    <SegmentsPiliers pilier={pilier} setPilier={setPilier} comptes={comptes} />
  );

  if (incidentSel && !idCourant)
    return (
      <>
        {segments}
        {incidents.some((i) => i.id === incidentSel)
          ? <Spinner texte="Ouverture de l'incident…" />
          : <div className="vide" role="status">Incident {incidentSel} introuvable dans la liste.</div>}
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
      {incidentsVue.length > 1 && (
        <nav className="dossiers" aria-label="Incidents du pilier">
          {incidentsVue.map((i) => (
            <button
              key={i.id}
              type="button"
              className={`dossier-puce ${i.id === idCourant ? "actif" : ""}`}
              aria-current={i.id === idCourant ? "true" : undefined}
              onClick={() => setIncidentSel(i.id)}
              title={i.titre}
            >
              <span className={`dossier-point statut-${i.statut ?? "ouvert"} etat-${i.etat}`} />
              <span className="dossier-id">{i.id}</span>
              <span className="dossier-type">{libelleType(i.type)}</span>
            </button>
          ))}
        </nav>
      )}

      {!detail || detail.id !== idCourant ? (
        <Spinner />
      ) : estIncidentAgent(detail) ? (
        <>
          {erreurDetail && <div className="decision-erreur" role="alert">{erreurDetail}</div>}
          <IncidentAgent
            incident={detail}
            majEnCours={chargeDetail}
            decisionEnCours={decisionEnCours}
            erreurDecision={erreurDecision}
            trancher={(a) => void trancher(a)}
          />
        </>
      ) : (
        <div className="incident-layout">
          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            <div className="panneau">
              <div className="corps">
                <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                  <span className={`gravite ${detail.gravite}`}>{detail.gravite}</span>
                  <BadgeTypeIncident type={detail.type} />
                  <BadgeEtat e={detail.etat} />
                  <span style={{ color: "var(--texte-faible)", fontFamily: "var(--mono)", fontSize: 12 }}>
                    {detail.id} · session {detail.session_id} · {detail.source}
                    {chargeDetail ? " · maj…" : ""}
                  </span>
                </div>
                <h2 style={{ marginTop: 10, fontSize: 18 }}>{detail.titre}</h2>
                <p style={{ color: "var(--texte-doux)", marginBottom: 0 }}>{detail.resume}</p>
              </div>
            </div>

            <GestePanneau incident={detail} />

            {erreurDetail && <div className="decision-erreur" role="alert">{erreurDetail}</div>}

            <div className="panneau">
              <div className="titre">
                Boîte noire — chaîne reconstruite
                <span className="droite">{detail.chaine?.length ?? 0} maillons</span>
              </div>
              <div className="corps">
                <div className="frise">
                  {(detail.chaine ?? [])
                    .slice()
                    .sort((a, b) => a.ordre - b.ordre)
                    .map((m) => (
                      <Maillon key={m.ordre} m={m} />
                    ))}
                </div>
              </div>
            </div>

            <DroitsPanneau incident={detail} sessions={sessions} />
          </div>

          <div className="colonne-decision">
            <div className="panneau">
              <div className="titre">Décision de l'analyste</div>
              <div className="corps">
                <p className="decision-contexte">
                  {estIncidentHumain(detail)
                    ? "Le SOC peut clore ou ignorer ce signal. Ces choix ne coupent pas le poste du salarié."
                    : detail.etat === "suspendue"
                      ? "L'agent est suspendu : la passerelle retient son appel jusqu'à la décision du SOC."
                      : detail.etat === "coupee"
                        ? "L'agent est coupé. La décision et son auteur restent dans le journal."
                        : "L'agent est actif. Le SOC peut encore décider de le couper si nécessaire."}
                </p>
                <div className="actions-analyste" aria-busy={decisionEnCours !== null}>
                  {(estIncidentHumain(detail) ? ACTIONS_HUMAIN : ACTIONS_AGENT).map((a) => (
                    <button
                      key={a.action}
                      className={`btn ${a.cls}`}
                      disabled={decisionEnCours !== null || detail.statut === "clos" || detail.statut === "ignore" ||
                        (a.action === "reprendre" && detail.etat !== "suspendue") ||
                        (a.action === "valider_riposte" && detail.etat !== "suspendue") ||
                        (a.action === "couper" && detail.etat === "coupee")}
                      onClick={() => void trancher(a.action)}
                    >
                      {decisionEnCours === a.action ? "Décision en cours…" : a.lib}
                    </button>
                  ))}
                </div>
                {erreurDecision && <p className="decision-erreur" role="alert">{erreurDecision}</p>}
                {(detail.statut === "clos" || detail.statut === "ignore" || detail.statut === "surveille") && (
                  <p className="decision-statut">Suivi : {detail.statut === "clos" ? "clos" : detail.statut === "ignore" ? "ignoré" : "sous surveillance"}</p>
                )}
                {detail.decisions?.length > 0 && (
                  <div style={{ marginTop: 14, fontSize: 12.5, color: "var(--texte-doux)" }}>
                    {detail.decisions.map((d, i) => (
                      <div key={i}>
                        <span style={{ fontFamily: "var(--mono)", color: "var(--accent)" }}>
                          {heure(d.horodatage)}
                        </span>{" "}
                        — {d.action.replace("_", " ")} par {d.analyste}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function Maillon({ m }: { m: MaillonChaine }) {
  return (
    <div className={`maillon phase-${m.phase}`}>
      <span className="puce">{PHASE_PIC[m.phase] ?? "•"}</span>
      <div className="m-titre">
        <span className="m-phase">{PHASE_LIB[m.phase] ?? m.phase.replace(/_/g, " ")}</span>
        <strong>{m.titre}</strong>
        <span className="m-heure">{heure(m.horodatage)}</span>
      </div>
      <div className="m-detail">{m.detail}</div>
      <div className="puces-tech">
        {m.choix && <BadgeChoixSalarie choix={m.choix} />}
        {m.leurre_id && <span className="tag leurre">leurre {m.leurre_id}</span>}
        {m.canari_id && <span className="tag leurre">canari {m.canari_id}</span>}
        {(m.techniques ?? []).map((t) => {
          const nom = nomTechnique(t.id, t.nom);
          return (
            <span
              key={t.id}
              className={`tag ${t.cadre === "ATLAS" ? "atlas" : "attack"}`}
              title={`${t.cadre} · ${nom}${t.a_confirmer ? " · rapprochement à confirmer" : ""}`}
            >
              {t.id} {nom}
              {t.a_confirmer && <span className="tag-doute">à confirmer</span>}
            </span>
          );
        })}
        {(m.risques ?? []).map((r) => (
          <span key={r.id} className="tag risque" title={r.nom}>
            {r.id.startsWith("OWASP") ? r.id : `OWASP ${r.id}`} · {r.nom}
          </span>
        ))}
      </div>
    </div>
  );
}

// Agent IA interne d'Orbis Pay : écran dédié (boîte noire en six maillons,
// couper / reprendre). Un incident humain n'y passe jamais.
function estIncidentAgent(inc: Incident): boolean {
  return !estIncidentHumain(inc) && (inc.source === "interne" || (inc.type ?? "").startsWith("interne_"));
}

// Un incident relève du pilier salariés s'il vient d'un poste/physique ou si
// son type commence par « humain_ ».
function estIncidentHumain(inc: Incident): boolean {
  return (
    inc.source === "humain" ||
    inc.source === "physique" ||
    (inc.type ?? "").startsWith("humain_")
  );
}

// Geste / avertissement / choix, lus sur l'incident d'abord, puis dans le
// maillon `avertissement` de la chaîne. Renvoie null si rien n'est connu.
function infosGeste(
  inc: Incident
): { geste?: string; avertissement?: string; choix?: ChoixSalarie } | null {
  const chaine = inc.chaine ?? [];
  const averti = [...chaine].reverse().find((x) => x.phase === "avertissement");
  const action = [...chaine].reverse().find((x) => x.phase === "action_risquee");
  const choixMaillon = [...chaine].reverse().find((x) => x.phase === "choix");
  const evenement = [...(inc.evenements ?? [])].reverse().find((e) => e.type === "avertissement");
  const details = evenement?.details ?? {};
  const texte = (valeur: unknown) => typeof valeur === "string" && valeur.trim() ? valeur.trim() : undefined;
  const brut = details.choix;
  const choix = inc.choix ?? averti?.choix ??
    (brut === "continuer" || brut === "annuler" ? brut : undefined) ??
    (choixMaillon?.detail.includes("annul") ? "annuler" :
      choixMaillon?.detail.includes("continuer") || choixMaillon?.detail.includes("passé outre") ? "continuer" : undefined);
  const geste = inc.geste ?? action?.detail;
  const avertissement = inc.avertissement ?? texte(details.message) ?? averti?.detail;
  if (!geste && !avertissement && !choix) return null;
  return { geste, avertissement, choix };
}

// Vue propre au pilier salariés : le geste risqué, le texte de l'avertissement
// affiché sur le poste, et le choix du salarié. Rendue seulement pour un
// incident humain qui porte au moins une de ces infos (dégradé propre sinon :
// la chaîne « boîte noire » suffit).
function GestePanneau({ incident }: { incident: Incident }) {
  if (!estIncidentHumain(incident)) return null;
  const infos = infosGeste(incident);
  if (!infos) return null;
  const { geste, avertissement, choix } = infos;
  const annule = choix === "annuler";
  const physique = incident.source === "physique";

  return (
    <div className="panneau">
      <div className="titre">
        {physique ? "Canari physique" : "Le garde du corps sur le poste"}
        <span className="droite">
          <BadgeChoixSalarie choix={choix} />
        </span>
      </div>
      <div className="corps">
        {geste && (
          <div className="geste-bloc">
            <div className="geste-lib">{physique ? "Accès détecté" : "Geste risqué repéré"}</div>
            <div className="geste-val">{geste}</div>
          </div>
        )}
        {avertissement && (
          <div className="geste-bloc">
            <div className="geste-lib">{physique ? "Signal du canari" : "Avertissement affiché au salarié"}</div>
            <div className="geste-popup">{avertissement}</div>
          </div>
        )}
        {choix && (
          <p
            className={`geste-verdict ${annule ? "bien" : "outre"}`}
            style={{ marginBottom: 0 }}
          >
            {annule
              ? "Le salarié a annulé après l'alerte : le geste risqué s'est arrêté là, avant d'aboutir."
              : "Le salarié est passé outre l'alerte. Le geste a été remonté au SOC."}
          </p>
        )}
      </div>
    </div>
  );
}

// Résout les droits à afficher : ceux portés par l'incident d'abord, sinon ceux
// de la session liée (champ optionnel). Absents → vue masquée (dégradé propre).
function droitsDeIncident(
  incident: Incident,
  sessions: Session[]
): DroitsAgent | null {
  if (incident.droits) return incident.droits;
  const s = sessions.find((x) => x.id === incident.session_id);
  return s?.droits ?? null;
}

// Vue « accès accordés vs nécessaires » : rend visible l'écart entre ce que
// l'agent peut faire et ce que sa tâche réclame. Absente proprement si aucun
// droit n'est connu (dégradé propre).
function DroitsPanneau({
  incident,
  sessions,
}: {
  incident: Incident;
  sessions: Session[];
}) {
  const droits = droitsDeIncident(incident, sessions);
  if (!droits) return null;

  const necessaires = new Set((droits.necessaires ?? []).map(codeDroit));
  const utilises = new Set((droits.utilises ?? []).map(codeDroit));
  const aUtilises = (droits.utilises ?? []).length > 0;

  const rangs = (droits.accordes ?? []).map((d) => {
    const code = codeDroit(d);
    const necessaire = necessaires.has(code);
    const utilise = utilises.has(code);
    return {
      d,
      code,
      necessaire,
      utilise,
      excedent: !necessaire,
    };
  });
  const nAccordes = rangs.length;
  const nNecessaires = necessaires.size;
  const nExcedent = rangs.filter((r) => r.excedent).length;

  return (
    <div className="panneau">
      <div className="titre">
        Accès accordés vs nécessaires
        <span className="droite">
          {nAccordes} accordés · {nNecessaires} nécessaire(s) · {nExcedent} en excès
        </span>
      </div>
      <div className="corps">
        <p style={{ color: "var(--texte-doux)", marginTop: 0 }}>
          Cet agent avait accès à bien plus que sa tâche : {nExcedent} droit(s)
          au-delà du strict nécessaire, autant de leviers pour un détournement.
        </p>
        <div className="droits-liste">
          {rangs.map((r) => (
            <div
              key={r.code}
              className={`droit-ligne ${r.necessaire ? "necessaire" : "excedent"}`}
            >
              <span className="droit-lib">{libDroit(r.d)}</span>
              <span className="droit-tags">
                {r.necessaire ? (
                  <span className="dtag ok">nécessaire</span>
                ) : (
                  <span className="dtag excedent">hors tâche</span>
                )}
                {aUtilises &&
                  (r.utilise ? (
                    <span className="dtag util">utilisé</span>
                  ) : (
                    <span className="dtag inutilise">jamais utilisé</span>
                  ))}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
