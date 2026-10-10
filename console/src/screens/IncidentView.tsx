import { useEffect, useMemo, useState } from "react";
import { useDonnees } from "../api/store";
import type { DecisionAction, Incident, MaillonChaine } from "../types";
import { BadgeEtat, heure, Spinner } from "../ui/primitives";

const PHASE_LIB: Record<MaillonChaine["phase"], string> = {
  entree: "Entrée",
  consigne: "Consigne lue",
  outil: "Appels d'outils",
  sortie: "Sortie de données",
  riposte: "Riposte",
};

const PHASE_PIC: Record<MaillonChaine["phase"], string> = {
  entree: "✉",
  consigne: "!",
  outil: "⚙",
  sortie: "⇲",
  riposte: "⛊",
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
}: {
  incidentSel: string | null;
  setIncidentSel: (id: string) => void;
}) {
  const { incidents, getIncident, decider, chargement } = useDonnees();

  const idCourant = useMemo(() => {
    if (incidentSel && incidents.some((i) => i.id === incidentSel))
      return incidentSel;
    return incidents[0]?.id ?? null;
  }, [incidentSel, incidents]);

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
  if (incidents.length === 0)
    return <div className="vide">Aucun incident ouvert. La surface est calme.</div>;

  return (
    <>
      {incidents.length > 1 && (
        <div className="panneau">
          <div className="corps" style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            {incidents.map((i) => (
              <button
                key={i.id}
                className={`btn ${i.id === idCourant ? "primaire" : "fantome"}`}
                onClick={() => setIncidentSel(i.id)}
              >
                {i.id} · {i.source}
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
