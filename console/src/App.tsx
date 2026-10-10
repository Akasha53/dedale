import { useEffect, useState } from "react";
import { useDonnees } from "./api/store";
import { LiveView } from "./screens/LiveView";
import { IncidentView } from "./screens/IncidentView";
import { LeurresView } from "./screens/LeurresView";
import { MesuresView } from "./screens/MesuresView";
import { pilierDeSource } from "./ui/primitives";
import type { Pilier } from "./types";

type Ecran = "temps-reel" | "incident" | "leurres" | "mesures";

// En-tête des écrans multi-piliers (temps réel, incident), recentré sur « l'humain,
// le maillon faible ». Les écrans d'agrégat (leurres, mesures) sont fixes.
const ENTETE_PILIER: Record<
  Pilier,
  { reel: { titre: string; desc: string }; incident: { titre: string; desc: string } }
> = {
  humain: {
    reel: {
      titre: "Salariés — l'humain, le maillon faible",
      desc: "Le garde du corps sur le poste repère le geste risqué avant qu'il n'aboutisse, prévient le salarié et le laisse choisir.",
    },
    incident: {
      titre: "Geste du salarié — boîte noire",
      desc: "Le geste risqué, l'avertissement affiché, le choix du salarié, et la décision du SOC.",
    },
  },
  interne: {
    reel: {
      titre: "Agents IA — temps réel",
      desc: "Second pilier : les agents IA d'Orbis Pay, surveillés quand un mail, un document ou un outil piégé les détourne.",
    },
    incident: {
      titre: "Agent IA détourné — boîte noire",
      desc: "Ce que l'agent a lu et tenté, ce que la passerelle a retenu. Vous coupez ou vous reprenez.",
    },
  },
};

const ENTETE_FIXE: Record<"leurres" | "mesures", { titre: string; desc: string }> = {
  leurres: {
    titre: "Leurres & canaris",
    desc: "Canaris des agents IA et canaris physiques, avec leur compteur de touches.",
  },
  mesures: {
    titre: "Mesures",
    desc: "Détection, faux positifs, temps de détection et de confinement.",
  },
};

function enteteDe(ecran: Ecran, pilier: Pilier): { titre: string; desc: string } {
  if (ecran === "temps-reel") return ENTETE_PILIER[pilier].reel;
  if (ecran === "incident") return ENTETE_PILIER[pilier].incident;
  return ENTETE_FIXE[ecran];
}

export function App() {
  const { mode, flux, incidents } = useDonnees();
  const [ecran, setEcran] = useState<Ecran>(() =>
    new URLSearchParams(window.location.search).has("incident") ? "incident" : "temps-reel"
  );
  // Pilier partagé entre temps réel et incidents. Par défaut : les salariés.
  const [pilier, setPilier] = useState<Pilier>("humain");
  const [incidentSel, setIncidentSel] = useState<string | null>(() =>
    new URLSearchParams(window.location.search).get("incident")
  );

  useEffect(() => {
    if (!incidentSel) return;
    const inc = incidents.find((i) => i.id === incidentSel);
    if (inc) setPilier(pilierDeSource(inc.source));
  }, [incidents, incidentSel]);

  useEffect(() => {
    const synchroniser = () => {
      const id = new URLSearchParams(window.location.search).get("incident");
      setIncidentSel(id);
      if (id) setEcran("incident");
    };
    window.addEventListener("popstate", synchroniser);
    return () => window.removeEventListener("popstate", synchroniser);
  }, []);

  const lierIncident = (id: string | null) => {
    const url = new URL(window.location.href);
    if (id) url.searchParams.set("incident", id);
    else url.searchParams.delete("incident");
    window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
    setIncidentSel(id);
  };

  const choisirPilier = (p: Pilier) => {
    setPilier(p);
    lierIncident(null);
  };

  const ouvrirIncident = (id: string) => {
    const inc = incidents.find((i) => i.id === id);
    if (inc) setPilier(pilierDeSource(inc.source));
    lierIncident(id);
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
            <div className="sous">L'humain, le maillon faible</div>
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
          <div className="note-laterale">
            Dédale prévient le salarié avant un geste risqué sur son poste et
            surveille les agents IA d'Orbis Pay.
          </div>
        </div>
      </aside>

      <main className="principal">
        <header className="entete">
          <div>
            <h1>{enteteDe(ecran, pilier).titre}</h1>
            <div className="desc">{enteteDe(ecran, pilier).desc}</div>
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

          {ecran === "temps-reel" && (
            <LiveView
              ouvrirIncident={ouvrirIncident}
              pilier={pilier}
              setPilier={choisirPilier}
            />
          )}
          {ecran === "incident" && (
            <IncidentView
              incidentSel={incidentSel}
              setIncidentSel={lierIncident}
              pilier={pilier}
              setPilier={choisirPilier}
            />
          )}
          {ecran === "leurres" && <LeurresView />}
          {ecran === "mesures" && <MesuresView />}

          <footer className="pied">
            L'humain est le maillon faible. Dédale protège d'abord le salarié
            contre ses propres gestes risqués (secret collé, envoi externe,
            upload vers une IA, phishing, intrusion), puis les agents IA
            d'Orbis Pay, et le SOC voit toute la chaîne. Orbis Pay est une
            fintech fictive, données synthétiques.
          </footer>
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
