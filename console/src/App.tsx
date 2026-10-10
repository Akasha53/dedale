import { useState } from "react";
import { useDonnees } from "./api/store";
import { LiveView } from "./screens/LiveView";
import { IncidentView } from "./screens/IncidentView";
import { LeurresView } from "./screens/LeurresView";
import { MesuresView } from "./screens/MesuresView";

type Ecran = "temps-reel" | "incident" | "leurres" | "mesures";

const ENTETES: Record<Ecran, { titre: string; desc: string }> = {
  "temps-reel": {
    titre: "Vue temps réel",
    desc: "Sessions en cours sur la surface d'Orbis Pay, classées et expliquées.",
  },
  incident: {
    titre: "Incident — boîte noire",
    desc: "Chaîne d'attaque reconstruite, décision de l'analyste, exports.",
  },
  leurres: {
    titre: "Leurres & canaris",
    desc: "Inventaire des pièges et compteur de touches.",
  },
  mesures: {
    titre: "Mesures",
    desc: "Détection, faux positifs, temps de détection et de confinement.",
  },
};

export function App() {
  const { mode, flux, incidents } = useDonnees();
  const [ecran, setEcran] = useState<Ecran>("temps-reel");
  const [incidentSel, setIncidentSel] = useState<string | null>(null);

  const ouvrirIncident = (id: string) => {
    setIncidentSel(id);
    setEcran("incident");
  };

  const nav = [
    { id: "temps-reel" as const, pic: "◉", lib: "Temps réel" },
    { id: "incident" as const, pic: "⬡", lib: "Incidents", compte: incidents.length },
    { id: "leurres" as const, pic: "⌘", lib: "Leurres" },
    { id: "mesures" as const, pic: "▦", lib: "Mesures" },
  ];

  return (
    <div className="app">
      <aside className="barre-laterale">
        <div className="logo">
          <div className="pastille-logo">D</div>
          <div>
            <div className="marque">Dédale</div>
            <div className="sous">Console SOC</div>
          </div>
        </div>
        {nav.map((n) => (
          <button
            key={n.id}
            className={`nav-item ${ecran === n.id ? "actif" : ""}`}
            onClick={() => setEcran(n.id)}
          >
            <span className="pic">{n.pic}</span>
            {n.lib}
            {n.compte != null && <span className="compte">{n.compte}</span>}
          </button>
        ))}
        <div className="bas-laterale">
          <div className="nav-item" style={{ cursor: "default" }}>
            <span className="pic">⌁</span>
            Orbis Pay (fictif)
          </div>
        </div>
      </aside>

      <main className="principal">
        <header className="entete">
          <div>
            <h1>{ENTETES[ecran].titre}</h1>
            <div className="desc">{ENTETES[ecran].desc}</div>
          </div>
          <IndicateurConnexion mode={mode} flux={flux} />
        </header>

        <div className="contenu">
          {mode === "mock" && (
            <div className="bandeau-mock">
              <span className="point mock" />
              Backend absent — données simulées (mock local). Bascule automatique
              dès que le backend répond sur 127.0.0.1:8700.
            </div>
          )}

          {ecran === "temps-reel" && <LiveView ouvrirIncident={ouvrirIncident} />}
          {ecran === "incident" && (
            <IncidentView
              incidentSel={incidentSel}
              setIncidentSel={setIncidentSel}
            />
          )}
          {ecran === "leurres" && <LeurresView />}
          {ecran === "mesures" && <MesuresView />}
        </div>
      </main>
    </div>
  );
}

function IndicateurConnexion({
  mode,
  flux,
}: {
  mode: string;
  flux: string;
}) {
  let cls = "point";
  let txt = "Connexion…";
  if (mode === "live") {
    if (flux === "connecte") {
      cls = "point ok";
      txt = "Backend connecté · flux WS";
    } else if (flux === "reconnexion") {
      cls = "point recon";
      txt = "Backend connecté · WS en reconnexion";
    } else {
      cls = "point recon";
      txt = "Backend connecté · WS absent";
    }
  } else if (mode === "mock") {
    cls = "point mock";
    txt = "Mock local";
  }
  return (
    <div className="etat-conn" title="État de la liaison au backend">
      <span className={cls} />
      {txt}
    </div>
  );
}
