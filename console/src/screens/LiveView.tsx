import { useState } from "react";
import { useDonnees } from "../api/store";
import type { Session } from "../types";
import {
  BadgeClassement,
  BadgeEtat,
  JaugeScore,
  Spinner,
  tempsRelatif,
} from "../ui/primitives";

export function LiveView({
  ouvrirIncident,
}: {
  ouvrirIncident: (id: string) => void;
}) {
  const { sessions, incidents, mesures, chargement } = useDonnees();

  const agents = sessions.filter((s) => s.classement === "agent_ia").length;
  const incidentsOuverts =
    mesures?.incidents_ouverts ??
    incidents.filter((i) => i.etat !== "coupee").length;

  const incidentParSession = new Map(incidents.map((i) => [i.session_id, i.id]));

  // Les plus suspects d'abord.
  const triees = [...sessions].sort((a, b) => b.score - a.score);

  return (
    <>
      <div className="grille-compteurs">
        <Compteur lib="Sessions actives" val={sessions.length} sous="sur la surface" />
        <Compteur
          lib="Agents IA détectés"
          val={agents}
          sous="classés agent_ia"
          alerte={agents > 0}
        />
        <Compteur
          lib="Incidents ouverts"
          val={incidentsOuverts}
          sous="riposte à trancher"
          alerte={incidentsOuverts > 0}
        />
        <Compteur
          lib="Leurres touchés"
          val={sessions.reduce((n, s) => n + (s.leurres_touches || 0), 0)}
          sous="cumul sessions"
        />
      </div>

      <div className="panneau">
        <div className="titre">
          Flux des sessions
          <span className="droite">score décroissant · survoler « signaux »</span>
        </div>
        {chargement ? (
          <Spinner texte="Connexion au flux…" />
        ) : triees.length === 0 ? (
          <div className="vide">Aucune session pour l'instant.</div>
        ) : (
          <div className="liste-sessions">
            {triees.map((s) => (
              <LigneSession
                key={s.id}
                s={s}
                incidentId={incidentParSession.get(s.id)}
                ouvrirIncident={ouvrirIncident}
              />
            ))}
          </div>
        )}
      </div>
    </>
  );
}

function Compteur({
  lib,
  val,
  sous,
  alerte,
}: {
  lib: string;
  val: number;
  sous: string;
  alerte?: boolean;
}) {
  return (
    <div className={`compteur ${alerte ? "alerte" : ""}`}>
      <div className="lib">{lib}</div>
      <div className="val">{val}</div>
      <div className="sous">{sous}</div>
    </div>
  );
}

function LigneSession({
  s,
  incidentId,
  ouvrirIncident,
}: {
  s: Session;
  incidentId?: string;
  ouvrirIncident: (id: string) => void;
}) {
  const [ouvert, setOuvert] = useState(false);
  return (
    <div className="session-ligne">
      <div className="idc">
        {s.id}
        <span className="srcv">{s.source}</span>
        {incidentId && (
          <span
            className="lien-incident"
            onClick={() => ouvrirIncident(incidentId)}
            role="button"
          >
            → {incidentId}
          </span>
        )}
      </div>

      <div>
        <BadgeClassement c={s.classement} />
        <div style={{ marginTop: 6, color: "var(--texte-faible)", fontSize: 12 }}>
          {s.leurres_touches > 0
            ? `${s.leurres_touches} leurre(s) touché(s)`
            : "aucun leurre touché"}{" "}
          · {tempsRelatif(s.derniere_vue)}
        </div>
      </div>

      <JaugeScore score={s.score} />

      <div style={{ display: "flex", flexDirection: "column", gap: 8, alignItems: "flex-end" }}>
        <BadgeEtat e={s.etat} />
        <div
          className="sig-wrap"
          onMouseEnter={() => setOuvert(true)}
          onMouseLeave={() => setOuvert(false)}
        >
          <button
            className="sig-btn"
            onClick={() => setOuvert((v) => !v)}
            aria-expanded={ouvert}
          >
            signaux ({s.signaux?.length ?? 0})
          </button>
          {ouvert && <PopSignaux s={s} />}
        </div>
      </div>
    </div>
  );
}

function PopSignaux({ s }: { s: Session }) {
  return (
    <div className="sig-pop">
      <h4>Pourquoi ce classement — {s.classement}</h4>
      {(s.signaux ?? []).length === 0 && (
        <div className="sig">
          <span className="lib">Pas encore de signal journalisé.</span>
        </div>
      )}
      {(s.signaux ?? []).map((sig, i) => (
        <div className="sig" key={i}>
          <span className="lib">{sig.libelle}</span>
          <span className={`poids ${sig.poids >= 0 ? "plus" : "moins"}`}>
            {sig.poids >= 0 ? "+" : ""}
            {sig.poids.toFixed(2)}
          </span>
          {sig.valeur && <span className="meta">{sig.valeur}</span>}
        </div>
      ))}
    </div>
  );
}
