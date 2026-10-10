import { useDonnees } from "../api/store";
import type { Classement, PointSerie, Session } from "../types";
import { LIB_CLASSEMENT, Spinner } from "../ui/primitives";

const COULEUR_CLASSEMENT: Record<Classement, string> = {
  humain: "var(--humain)",
  script: "var(--script)",
  agent_ia: "var(--agent)",
  inconnu: "var(--inconnu)",
};

export function MesuresView() {
  const { mesures, chargement, sessions, incidents } = useDonnees();

  if (chargement) return <Spinner />;
  if (!mesures)
    return <div className="vide">Mesures indisponibles (backend muet).</div>;

  const repartition = repartitionDe(sessions);
  const pctDet = mesures.taux_detection == null ? null : Math.round(mesures.taux_detection * 100);
  const pctFP = mesures.faux_positifs == null ? null : Math.round(mesures.faux_positifs * 100);

  return (
    <>
      <div className="grille-mesures">
        <Kpi lib="Taux de détection" val={pctDet == null ? "—" : `${pctDet} %`} cls={pctDet == null ? "" : "bon"} />
        <Kpi lib="Faux positifs" val={pctFP == null ? "—" : `${pctFP} %`} cls={pctFP == null ? "" : pctFP > 10 ? "att" : "bon"} />
        <Kpi lib="Temps de détection (méd.)" val={mesures.temps_detection_s == null ? "—" : `${mesures.temps_detection_s} s`} />
        <Kpi lib="Temps de confinement (méd.)" val={mesures.temps_confinement_s == null ? "—" : `${mesures.temps_confinement_s} s`} />
      </div>

      <div className="grille-mesures">
        {/* Totaux comptés ici, sur les deux piliers de la console : ceux du
            backend incluent la surface externe. */}
        <Kpi lib="Sessions observées" val={String(sessions.length)} />
        <Kpi lib="Agents IA détectés" val={String(repartition.agent_ia)} cls="att" />
        <Kpi lib="Incidents ouverts" val={String(incidents.filter((i) => !i.statut || i.statut === "ouvert").length)} cls="att" />
        <Kpi lib="Incidents clos" val={String(incidents.filter((i) => i.statut === "clos" || i.statut === "ignore").length)} />
      </div>

      <div className="graphes">
        <div className="panneau">
          <div className="titre">
            Taux de détection
            <span className="droite">7 derniers points</span>
          </div>
          <div className="corps">
            {mesures.taux_detection == null
              ? <div className="vide">Taux indisponible sans vérité terrain.</div>
              : <GrapheLigne points={mesures.serie_detection} />}
          </div>
        </div>

        <div className="panneau">
          <div className="titre">Répartition des sessions</div>
          <div className="corps">
            <GrapheBarres repartition={repartition} />
          </div>
        </div>
      </div>
    </>
  );
}

// Même calcul que backend/app/mesures.py, sur les sessions affichées.
function repartitionDe(sessions: Session[]): Record<Classement, number> {
  const r: Record<Classement, number> = { humain: 0, script: 0, agent_ia: 0, inconnu: 0 };
  for (const s of sessions) if (s.classement in r) r[s.classement] += 1;
  return r;
}

function Kpi({ lib, val, cls = "" }: { lib: string; val: string; cls?: string }) {
  return (
    <div className="kpi">
      <div className="lib">{lib}</div>
      <div className={`val ${cls}`}>{val}</div>
    </div>
  );
}

function GrapheLigne({ points }: { points: PointSerie[] }) {
  if (!points || points.length < 2)
    return <div className="vide">Pas assez de points.</div>;
  const W = 560;
  const H = 180;
  const P = 28;
  const max = 1; // taux 0..1
  const min = Math.max(0, Math.min(...points.map((p) => p.valeur)) - 0.1);
  const x = (i: number) => P + (i * (W - 2 * P)) / (points.length - 1);
  const y = (v: number) => H - P - ((v - min) / (max - min)) * (H - 2 * P);
  const d = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(p.valeur)}`).join(" ");
  const aire = `${d} L${x(points.length - 1)},${H - P} L${x(0)},${H - P} Z`;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Taux de détection dans le temps">
      {[0, 0.25, 0.5, 0.75, 1].map((g) => (
        <g key={g}>
          <line
            x1={P}
            x2={W - P}
            y1={y(min + (max - min) * g)}
            y2={y(min + (max - min) * g)}
            stroke="var(--bord)"
            strokeDasharray="3 4"
          />
        </g>
      ))}
      <path d={aire} fill="color-mix(in srgb, var(--accent) 16%, transparent)" />
      <path d={d} fill="none" stroke="var(--accent)" strokeWidth={2.5} strokeLinejoin="round" />
      {points.map((p, i) => (
        <circle key={i} cx={x(i)} cy={y(p.valeur)} r={3.5} fill="var(--accent)" />
      ))}
      {points.map((p, i) => (
        <text
          key={i}
          x={x(i)}
          y={H - 8}
          fill="var(--texte-faible)"
          fontSize="10"
          textAnchor="middle"
        >
          {p.t}
        </text>
      ))}
    </svg>
  );
}

function GrapheBarres({ repartition }: { repartition: Record<Classement, number> }) {
  const entrees = (Object.keys(repartition) as Classement[]).map((c) => ({
    c,
    n: repartition[c] ?? 0,
  }));
  const max = Math.max(1, ...entrees.map((e) => e.n));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {entrees.map(({ c, n }) => (
        <div key={c} style={{ display: "grid", gridTemplateColumns: "92px 1fr 28px", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 12.5, color: "var(--texte-doux)" }}>{LIB_CLASSEMENT[c]}</span>
          <div className="barre" style={{ height: 14, background: "var(--fond)", border: "1px solid var(--bord)", borderRadius: 6, overflow: "hidden" }}>
            <span
              style={{
                display: "block",
                height: "100%",
                width: `${(n / max) * 100}%`,
                background: COULEUR_CLASSEMENT[c],
                borderRadius: 6,
              }}
            />
          </div>
          <span style={{ fontFamily: "var(--mono)", fontSize: 13, textAlign: "right" }}>{n}</span>
        </div>
      ))}
    </div>
  );
}
