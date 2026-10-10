import { useEffect, useMemo, useState } from "react";
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

const PHASE_LIB: Record<MaillonChaine["phase"], string> = {
  entree: "Entrée",
  consigne: "Consigne lue",
  outil: "Appels d'outils",
  sortie: "Sortie de données",
  riposte: "Riposte",
  avertissement: "Avertissement au salarié",
};

const PHASE_PIC: Record<MaillonChaine["phase"], string> = {
  entree: "✉",
  consigne: "!",
  outil: "⚙",
  sortie: "⇲",
  riposte: "⛊",
  avertissement: "⚠",
};

const VIDE_PILIER: Record<Pilier, string> = {
  humain: "Aucun geste risqué de salarié en incident. Les postes sont calmes.",
  interne: "Aucun incident interne ouvert. Les agents d'Orbis Pay sont calmes.",
  externe: "Aucun incident externe en réserve.",
};

const ACTIONS: { action: DecisionAction; lib: string; cls: string }[] = [
  { action: "valider_riposte", lib: "Valider la riposte", cls: "primaire" },
  { action: "couper", lib: "Couper", cls: "danger" },
  { action: "reprendre", lib: "Reprendre", cls: "fantome" },
  { action: "ignorer", lib: "Ignorer", cls: "fantome" },
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
    const c = { humain: 0, interne: 0, externe: 0 } as Record<Pilier, number>;
    for (const p of PILIERS)
      c[p.id] = incidents.filter((i) => appartientPilier(i.source, p.id)).length;
    return c;
  }, [incidents]);

  const idCourant = useMemo(() => {
    if (incidentSel && incidentsVue.some((i) => i.id === incidentSel))
      return incidentSel;
    return incidentsVue[0]?.id ?? null;
  }, [incidentSel, incidentsVue]);

  const [detail, setDetail] = useState<Incident | null>(null);
  const [chargeDetail, setChargeDetail] = useState(false);

  useEffect(() => {
    if (!idCourant) {
      setDetail(null);
      return;
    }
    let vivant = true;
    // On part de la version de la liste (souvent complète), puis on récupère le
    // détail à jour.
    setDetail(incidents.find((i) => i.id === idCourant) ?? null);
    setChargeDetail(true);
    getIncident(idCourant)
      .then((d) => vivant && setDetail(d))
      .catch(() => {})
      .finally(() => vivant && setChargeDetail(false));
    return () => {
      vivant = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idCourant, getIncident]);

  const trancher = async (action: DecisionAction) => {
    if (!idCourant) return;
    await decider(idCourant, action, "analyste-soc");
    try {
      setDetail(await getIncident(idCourant));
    } catch {
      /* ignore */
    }
  };

  if (chargement) return <Spinner />;

  const segments = (
    <SegmentsPiliers pilier={pilier} setPilier={setPilier} comptes={comptes} />
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
        <div className="panneau">
          <div className="corps" style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            {incidentsVue.map((i) => (
              <button
                key={i.id}
                className={`btn ${i.id === idCourant ? "primaire" : "fantome"}`}
                onClick={() => setIncidentSel(i.id)}
                title={libelleType(i.type)}
              >
                {i.id} · {libelleType(i.type)}
              </button>
            ))}
          </div>
        </div>
      )}

      {!detail ? (
        <Spinner />
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

            <div className="panneau">
              <div className="titre">Décision de l'analyste</div>
              <div className="corps">
                <div className="actions-analyste">
                  {ACTIONS.map((a) => (
                    <button
                      key={a.action}
                      className={`btn ${a.cls}`}
                      disabled={detail.etat === "coupee" && a.action !== "ignorer"}
                      onClick={() => trancher(a.action)}
                    >
                      {a.lib}
                    </button>
                  ))}
                </div>
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

          <PanneauLateral incident={detail} />
        </div>
      )}
    </>
  );
}

function Maillon({ m }: { m: MaillonChaine }) {
  return (
    <div className={`maillon phase-${m.phase}`}>
      <span className="puce">{PHASE_PIC[m.phase]}</span>
      <div className="m-titre">
        <span className="m-phase">{PHASE_LIB[m.phase]}</span>
        <strong>{m.titre}</strong>
        <span className="m-heure">{heure(m.horodatage)}</span>
      </div>
      <div className="m-detail">{m.detail}</div>
      <div className="puces-tech">
        {m.choix && <BadgeChoixSalarie choix={m.choix} />}
        {m.leurre_id && <span className="tag leurre">leurre {m.leurre_id}</span>}
        {m.canari_id && <span className="tag leurre">canari {m.canari_id}</span>}
        {(m.techniques ?? []).map((t) => (
          <span
            key={t.id}
            className={`tag ${t.cadre === "ATLAS" ? "atlas" : "attack"}`}
            title={`${t.cadre} · ${t.nom}`}
          >
            {t.id} {t.nom}
          </span>
        ))}
        {(m.risques ?? []).map((r) => (
          <span key={r.id} className="tag risque" title={r.nom}>
            OWASP {r.id} · {r.nom}
          </span>
        ))}
      </div>
    </div>
  );
}

function PanneauLateral({ incident }: { incident: Incident }) {
  const { nis2, exporter } = useDonnees();
  const [nis2Texte, setNis2Texte] = useState("");
  const [format, setFormat] = useState<"ecs" | "sigma">("ecs");
  const [exportTexte, setExportTexte] = useState("");
  const [copie, setCopie] = useState<string | null>(null);

  useEffect(() => {
    let vivant = true;
    nis2(incident.id)
      .then((t) => vivant && setNis2Texte(t))
      .catch(() => vivant && setNis2Texte("Brouillon indisponible."));
    return () => {
      vivant = false;
    };
  }, [incident.id, nis2]);

  useEffect(() => {
    let vivant = true;
    exporter(incident.id, format)
      .then((t) => vivant && setExportTexte(t))
      .catch(() => vivant && setExportTexte("Export indisponible."));
    return () => {
      vivant = false;
    };
  }, [incident.id, format, exporter]);

  const copier = async (quoi: string, texte: string) => {
    try {
      await navigator.clipboard.writeText(texte);
      setCopie(quoi);
      setTimeout(() => setCopie(null), 1800);
    } catch {
      setCopie(null);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18, position: "sticky", top: 90 }}>
      <div className="panneau">
        <div className="titre">Notification NIS2 (24 h)</div>
        <div className="corps">
          <textarea className="zone-texte" value={nis2Texte} readOnly />
          <div className="rangee-bouton">
            <button className="btn fantome" onClick={() => copier("nis2", nis2Texte)}>
              Copier
            </button>
            {copie === "nis2" && <span className="copie-ok">copié ✓</span>}
          </div>
        </div>
      </div>

      <div className="panneau">
        <div className="titre">
          Export SIEM
          <span className="droite">
            <span className="onglets-mini">
              <button className={format === "ecs" ? "actif" : ""} onClick={() => setFormat("ecs")}>
                ECS
              </button>
              <button className={format === "sigma" ? "actif" : ""} onClick={() => setFormat("sigma")}>
                Sigma
              </button>
            </span>
          </span>
        </div>
        <div className="corps">
          <textarea className="zone-texte" value={exportTexte} readOnly />
          <div className="rangee-bouton">
            <button
              className="btn fantome"
              onClick={() => copier("export", exportTexte)}
            >
              Copier ({format.toUpperCase()})
            </button>
            {copie === "export" && <span className="copie-ok">copié ✓</span>}
          </div>
        </div>
      </div>
    </div>
  );
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
  const m = (inc.chaine ?? []).find((x) => x.phase === "avertissement");
  const geste = inc.geste;
  const avertissement = inc.avertissement ?? m?.detail;
  const choix = inc.choix ?? m?.choix;
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

  return (
    <div className="panneau">
      <div className="titre">
        Le garde du corps sur le poste
        <span className="droite">
          <BadgeChoixSalarie choix={choix} />
        </span>
      </div>
      <div className="corps">
        {geste && (
          <div className="geste-bloc">
            <div className="geste-lib">Geste risqué repéré</div>
            <div className="geste-val">{geste}</div>
          </div>
        )}
        {avertissement && (
          <div className="geste-bloc">
            <div className="geste-lib">Avertissement affiché au salarié</div>
            <div className="geste-popup">{avertissement}</div>
          </div>
        )}
        {choix && (
          <p
            className={`geste-verdict ${annule ? "bien" : "outre"}`}
            style={{ marginBottom: 0 }}
          >
            {annule
              ? "Le salarié a annulé après l'alerte : le geste risqué a été arrêté à temps. C'est la protection qui marche."
              : "Le salarié est passé outre l'alerte : le geste a eu lieu. Dédale l'a attrapé au moment du clic et l'escalade au SOC."}
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
