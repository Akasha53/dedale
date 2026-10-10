import { useEffect, useMemo, useState } from "react";
import { useDonnees } from "./api/store";
import { LiveView } from "./screens/LiveView";
import { IncidentView } from "./screens/IncidentView";
import { MesuresView } from "./screens/MesuresView";
import { pilierDeSource } from "./ui/primitives";
import { compter } from "./ui/compteurs";
import { SelecteurAnalyste } from "./ui/analyste";
import { Icone } from "./agent/icones";
import logoDedale from "./assets/dedale.svg";
import type { Pilier } from "./types";

// La page « Leurres » (screens/LeurresView.tsx) est sortie de la navigation :
// les leurres externes sont abandonnés et le volet physique passe dans la
// feuille de route. Décision réversible : le fichier reste en place.
type Ecran = "temps-reel" | "incident" | "mesures";

const ENTETE_PILIER: Record<
  Pilier,
  { reel: { titre: string; desc: string }; incident: { titre: string; desc: string } }
> = {
  interne: {
    reel: {
      titre: "Agents IA en direct",
      desc: "Chaque action d'un agent passe par Dédale. Une action douteuse attend votre décision.",
    },
    incident: {
      titre: "Incidents des agents IA",
      desc: "Ce que l'agent a lu, ce qu'il a tenté, et ce que vous décidez.",
    },
  },
  humain: {
    reel: {
      titre: "Salariés en direct",
      desc: "Dédale prévient le salarié avant un geste risqué et le laisse choisir. Les noms restent masqués.",
    },
    incident: {
      titre: "Incidents des salariés",
      desc: "Le geste risqué, l'alerte affichée et ce que le salarié a choisi.",
    },
  },
};

const ENTETE_MESURES = {
  titre: "Mesures",
  desc: "Ce que Dédale repère, ce qu'il rate, et à quelle vitesse.",
};

function enteteDe(ecran: Ecran, pilier: Pilier): { titre: string; desc: string } {
  if (ecran === "temps-reel") return ENTETE_PILIER[pilier].reel;
  if (ecran === "incident") return ENTETE_PILIER[pilier].incident;
  return ENTETE_MESURES;
}

export function App() {
  const { incidents, sessions, inventaire, activite } = useDonnees();
  const [ecran, setEcran] = useState<Ecran>(() =>
    new URLSearchParams(window.location.search).has("incident") ? "incident" : "temps-reel"
  );
  // Pilier partagé entre temps réel et incidents. Par défaut : les agents IA.
  const [pilier, setPilier] = useState<Pilier>("interne");
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

  // Même nombre que les onglets et les compteurs : une seule source (ui/compteurs.ts).
  const comptes = useMemo(() => compter(incidents, sessions, inventaire, activite), [incidents, sessions, inventaire, activite]);
  const aTrancher = comptes.aTraiter.humain + comptes.aTraiter.interne;
  const nav = [
    { id: "temps-reel" as const, pic: "direct" as const, lib: "Temps réel" },
    { id: "incident" as const, pic: "incidents" as const, lib: "Incidents", compte: aTrancher },
    { id: "mesures" as const, pic: "mesures" as const, lib: "Mesures" },
  ];
  const entete = enteteDe(ecran, pilier);

  return (
    <div className="app">
      <aside className="barre-laterale">
        <div className="logo">
          <img className="logo-dedale" src={logoDedale} width={28} height={28} alt="" />
          <div>
            <div className="marque">Dédale</div>
            <div className="sous">Console de sécurité</div>
          </div>
        </div>
        {nav.map((n) => (
          <button
            key={n.id}
            className={`nav-item ${ecran === n.id ? "actif" : ""}`}
            onClick={() => setEcran(n.id)}
          >
            <span className="pic">
              <Icone nom={n.pic} taille={18} />
            </span>
            {n.lib}
            {n.compte != null && n.compte > 0 && (
              <span className="compte" title="Dossiers à traiter">{n.compte}</span>
            )}
          </button>
        ))}
        <div className="bas-laterale">
          <div className="nav-item" style={{ cursor: "default" }}>
            <span className="pic">
              <Icone nom="entreprise" taille={18} />
            </span>
            Orbis Pay
          </div>
          <div className="note-laterale">
            Dédale surveille les agents IA d'Orbis Pay et prévient les salariés
            avant un geste risqué.
          </div>
        </div>
      </aside>

      <main className="principal">
        <header className="entete">
          <div>
            <h1>{entete.titre}</h1>
            <div className="desc">{entete.desc}</div>
          </div>
          <SelecteurAnalyste />
        </header>

        <div className="contenu">
          {ecran === "temps-reel" && (
            <LiveView ouvrirIncident={ouvrirIncident} pilier={pilier} setPilier={choisirPilier} />
          )}
          {ecran === "incident" && (
            <IncidentView
              incidentSel={incidentSel}
              setIncidentSel={lierIncident}
              pilier={pilier}
              setPilier={choisirPilier}
            />
          )}
          {ecran === "mesures" && <MesuresView />}
        </div>
      </main>
    </div>
  );
}
