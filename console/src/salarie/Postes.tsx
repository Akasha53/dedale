// Les postes des salariés, sous pseudonyme. Pas de score : Dédale prévient un
// salarié, il ne le note pas. Un poste compte une fois, qu'il remonte par son
// poste, sa boîte mail ou son navigateur.
//
// Trois groupes, dans cet ordre : les postes qui ont un dossier à traiter (seule
// couleur du bloc), ceux dont le geste risqué est déjà traité (gris, avec leur
// dossier), puis les postes calmes, repliés en une ligne.

import { useMemo, useState } from "react";
import type { Incident, Session } from "../types";
import { Depliant } from "../agent/Depliant";
import { clePoste } from "../ui/compteurs";
import { estATraiter, etatIncident, titreIncident } from "../ui/mots";
import { appartientPilier, tempsRelatif } from "../ui/primitives";

const ORDRE_CANAUX = ["poste", "boîte mail", "navigateur", "signalement"];

function canal(id: string): string {
  if (id.startsWith("mail-")) return "boîte mail";
  if (id.startsWith("navigateur-")) return "navigateur";
  if (id.includes("signalement")) return "signalement";
  return "poste";
}

interface Poste {
  cle: string;
  pseudonyme: string;
  service?: string | null;
  canaux: string[];
  derniere?: string;
  incidents: Incident[];
  aTraiter: Incident[];
}

const plusRecent = (a?: string, b?: string) => (b ?? "").localeCompare(a ?? "");

export function ListePostes({
  sessions,
  incidents,
  ouvrirIncident,
}: {
  sessions: Session[];
  incidents: Incident[];
  ouvrirIncident: (id: string) => void;
}) {
  const [calmesOuverts, setCalmesOuverts] = useState(false);

  const { actifs, traites, calmes } = useMemo(() => {
    const parCle = new Map<string, Poste>();
    for (const s of sessions.filter((x) => appartientPilier(x.source, "humain"))) {
      const cle = clePoste(s);
      const p = parCle.get(cle) ?? {
        cle,
        pseudonyme: s.identite?.pseudonyme ?? s.identite?.libelle ?? "Salarié",
        service: s.identite?.service,
        canaux: [],
        incidents: [],
        aTraiter: [],
      };
      if (!p.service && s.identite?.service) p.service = s.identite.service;
      const c = canal(s.id);
      if (!p.canaux.includes(c)) p.canaux.push(c);
      if (!p.derniere || (s.derniere_vue ?? "") > p.derniere) p.derniere = s.derniere_vue;
      p.incidents.push(...incidents.filter((i) => i.session_id === s.id));
      parCle.set(cle, p);
    }
    const tous = [...parCle.values()].map((p) => {
      p.canaux.sort((a, b) => ORDRE_CANAUX.indexOf(a) - ORDRE_CANAUX.indexOf(b));
      p.incidents.sort((a, b) => plusRecent(a.ouvert_le, b.ouvert_le));
      return { ...p, aTraiter: p.incidents.filter(estATraiter) };
    });
    return {
      actifs: tous
        .filter((p) => p.aTraiter.length > 0)
        .sort((a, b) => plusRecent(a.aTraiter[0].ouvert_le, b.aTraiter[0].ouvert_le)),
      traites: tous
        .filter((p) => p.aTraiter.length === 0 && p.incidents.length > 0)
        .sort((a, b) => plusRecent(a.derniere, b.derniere)),
      calmes: tous.filter((p) => p.incidents.length === 0).sort((a, b) => plusRecent(a.derniere, b.derniere)),
    };
  }, [sessions, incidents]);

  const total = actifs.length + traites.length + calmes.length;
  if (total === 0) return <div className="vide">Aucun poste protégé pour l'instant.</div>;

  const visibles = actifs.length + traites.length > 0 || calmesOuverts;

  return (
    <div className="postes" role="table" aria-label="Postes des salariés">
      {visibles && (
        <div className="poste-ligne poste-tete" role="row">
          <span role="columnheader">Poste</span>
          <span role="columnheader">Sources</span>
          <span role="columnheader">Activité</span>
          <span role="columnheader">État</span>
          <span role="columnheader">Dernier geste</span>
          <span role="columnheader" className="poste-action">
            <span className="sr-seul">Dossier</span>
          </span>
        </div>
      )}
      {actifs.map((p) => (
        <LignePoste key={p.cle} p={p} ton="actif" ouvrirIncident={ouvrirIncident} />
      ))}
      {traites.map((p) => (
        <LignePoste key={p.cle} p={p} ton="traite" ouvrirIncident={ouvrirIncident} />
      ))}
      {calmes.length > 0 && (
        <div className="postes-calmes" role="rowgroup">
          <div role="row">
            <button
              type="button"
              className={`postes-calmes-btn ${calmesOuverts ? "ouvert" : ""}`}
              aria-expanded={calmesOuverts}
              aria-controls="postes-calmes-liste"
              onClick={() => setCalmesOuverts((v) => !v)}
            >
              {calmes.length} poste{calmes.length > 1 ? "s" : ""} sans rien à signaler
              <span className="postes-chevron" aria-hidden="true" />
            </button>
          </div>
          <Depliant ouvert={calmesOuverts} id="postes-calmes-liste">
            {calmes.map((p) => (
              <LignePoste key={p.cle} p={p} ton="calme" ouvrirIncident={ouvrirIncident} />
            ))}
          </Depliant>
        </div>
      )}
    </div>
  );
}

function LignePoste({
  p,
  ton,
  ouvrirIncident,
}: {
  p: Poste;
  ton: "actif" | "traite" | "calme";
  ouvrirIncident: (id: string) => void;
}) {
  const inc = ton === "actif" ? p.aTraiter[0] : p.incidents[0];
  const n = p.aTraiter.length;
  const sources = p.canaux.join(", ");
  const vu = tempsRelatif(p.derniere);
  const etat = ton === "actif" ? (n > 1 ? `${n} à traiter` : etatIncident(inc).lib) : ton === "traite" ? "Traité" : "";

  return (
    <div className={`poste-ligne poste-${ton}`} role="row">
      <span className="poste-nom" role="cell">
        <span className="poste-pseudo">{p.pseudonyme}</span>
        {p.service && <span className="poste-service">{p.service}</span>}
      </span>
      <span className="poste-sources" role="cell">{sources}</span>
      <span className="poste-activite" role="cell">{vu}</span>
      <span className="poste-meta">
        {sources} · {vu}
      </span>
      <span className="poste-etat" role="cell">
        {etat && (
          <span className={`poste-etat-lib e-${ton}`}>
            <span className="pt" aria-hidden="true" />
            {etat}
          </span>
        )}
      </span>
      <span className="poste-geste" role="cell" title={inc ? titreIncident(inc) : undefined}>
        {inc ? titreIncident(inc) : ""}
      </span>
      <span className="poste-action" role="cell">
        {inc && (
          <button type="button" className="poste-voir" onClick={() => ouvrirIncident(inc.id)}>
            Voir le dossier
          </button>
        )}
      </span>
    </div>
  );
}
