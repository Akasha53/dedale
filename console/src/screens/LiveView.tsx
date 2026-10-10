import { useMemo, useState } from "react";
import { useDonnees } from "../api/store";
import type { Incident, Pilier, Session } from "../types";
import {
  appartientPilier,
  BadgeClassement,
  BadgeEtat,
  JaugeScore,
  PILIERS,
  SegmentsPiliers,
  Spinner,
  tempsRelatif,
} from "../ui/primitives";

// Choix du salarié résolu depuis l'incident (champ direct, sinon maillon
// `avertissement` de la chaîne). Renvoie null si inconnu.
function choixIncident(i: Incident): "continuer" | "annuler" | null {
  if (i.choix) return i.choix;
  const m = (i.chaine ?? []).find((x) => x.phase === "avertissement" && x.choix);
  return m?.choix ?? null;
}

// Compteurs propres à chaque pilier. Pour les salariés, on met en tête le
// nombre de salariés surveillés et les gestes risqués arrêtés (l'argument).
function compteursPilier(
  pilier: Pilier,
  dansVue: Session[],
  incidentsVue: Incident[]
): { lib: string; val: number; sous: string; alerte?: boolean }[] {
  const incidentsOuverts = incidentsVue.filter((i) => i.etat !== "coupee").length;
  if (pilier === "humain") {
    const arretes = incidentsVue.filter((i) => choixIncident(i) === "annuler").length;
    const passesOutre = incidentsVue.filter((i) => choixIncident(i) === "continuer").length;
    return [
      { lib: "Salariés surveillés", val: dansVue.length, sous: "postes sous garde du corps" },
      {
        lib: "Gestes risqués arrêtés",
        val: arretes,
        sous: "le salarié a annulé à temps",
      },
      {
        lib: "Gestes passés outre",
        val: passesOutre,
        sous: "incident malgré l'alerte",
        alerte: passesOutre > 0,
      },
      {
        lib: "À trancher par le SOC",
        val: incidentsOuverts,
        sous: "incidents ouverts",
        alerte: incidentsOuverts > 0,
      },
    ];
  }
  const agents = dansVue.filter((s) => s.classement === "agent_ia").length;
  const leurresTouches = dansVue.reduce((n, s) => n + (s.leurres_touches || 0), 0);
  if (pilier === "interne") {
    return [
      { lib: "Agents internes surveillés", val: dansVue.length, sous: "agents IA d'Orbis Pay" },
      { lib: "Agents internes détournés", val: agents, sous: "classés agent_ia", alerte: agents > 0 },
      { lib: "Incidents internes ouverts", val: incidentsOuverts, sous: "riposte à trancher", alerte: incidentsOuverts > 0 },
      { lib: "Canaris touchés", val: leurresTouches, sous: "cumul sessions", alerte: leurresTouches > 0 },
    ];
  }
  return [
    { lib: "Sessions externes", val: dansVue.length, sous: "surface exposée (réserve)" },
    { lib: "Agents IA externes", val: agents, sous: "classés agent_ia", alerte: agents > 0 },
    { lib: "Incidents externes ouverts", val: incidentsOuverts, sous: "riposte à trancher", alerte: incidentsOuverts > 0 },
    { lib: "Leurres touchés", val: leurresTouches, sous: "cumul sessions" },
  ];
}

const TITRE_FLUX: Record<Pilier, string> = {
  humain: "Flux des postes salariés",
  interne: "Flux des agents internes",
  externe: "Flux de la surface externe (réserve)",
};
const VIDE_FLUX: Record<Pilier, string> = {
  humain: "Aucun poste salarié surveillé pour l'instant.",
  interne: "Aucun agent interne surveillé pour l'instant.",
  externe: "Aucune session externe en réserve.",
};

export function LiveView({
  ouvrirIncident,
  pilier,
  setPilier,
}: {
  ouvrirIncident: (id: string) => void;
  pilier: Pilier;
  setPilier: (p: Pilier) => void;
}) {
  const { sessions, incidents, chargement } = useDonnees();

  const dansVue = sessions.filter((s) => appartientPilier(s.source, pilier));
  const incidentsVue = incidents.filter((i) => appartientPilier(i.source, pilier));

  const comptes = useMemo(() => {
    const c = { humain: 0, interne: 0, externe: 0 } as Record<Pilier, number>;
    for (const p of PILIERS)
      c[p.id] = sessions.filter((s) => appartientPilier(s.source, p.id)).length;
    return c;
  }, [sessions]);

  const compteurs = compteursPilier(pilier, dansVue, incidentsVue);
  const incidentParSession = new Map(incidents.map((i) => [i.session_id, i.id]));

  // Les plus suspects d'abord.
  const triees = [...dansVue].sort((a, b) => b.score - a.score);

  return (
    <>
      <SegmentsPiliers pilier={pilier} setPilier={setPilier} comptes={comptes} />

      <div className="grille-compteurs">
        {compteurs.map((c) => (
          <Compteur key={c.lib} lib={c.lib} val={c.val} sous={c.sous} alerte={c.alerte} />
        ))}
      </div>

      <div className="panneau">
        <div className="titre">
          {TITRE_FLUX[pilier]}
          <span className="droite">score décroissant · survoler « signaux »</span>
        </div>
        {chargement ? (
          <Spinner texte="Connexion au flux…" />
        ) : triees.length === 0 ? (
          <div className="vide">{VIDE_FLUX[pilier]}</div>
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
