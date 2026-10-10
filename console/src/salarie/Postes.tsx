// Les postes des salariés, sous pseudonyme. Pas de score : Dédale prévient un
// salarié, il ne le note pas. Un poste compte une fois, qu'il remonte par son
// poste, sa boîte mail ou son navigateur.
//
// Seuls les postes qui ont un dossier à traiter s'affichent en ligne : c'est la
// seule couleur du bloc. Tous les autres, dossier traité ou rien à signaler, se
// replient en une ligne (« 7 postes sans rien à traiter », « dont 1 dossier
// traité aujourd'hui »). Dépliés, les postes traités viennent d'abord, en gris,
// avec leur dossier. Un élément déjà traité ne passe jamais au-dessus de ce qui
// demande un geste.

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

// Quand le dossier a été traité : la décision, sinon son ouverture.
function dateTraitement(i: Incident): string | undefined {
  return i.decide_a ?? i.decisions?.[i.decisions.length - 1]?.horodatage ?? i.ouvert_le;
}

function estAujourdhui(iso?: string | null): boolean {
  if (!iso) return false;
  const d = new Date(iso);
  return !Number.isNaN(d.getTime()) && d.toDateString() === new Date().toDateString();
}

export function ListePostes({
  sessions,
  incidents,
  ouvrirIncident,
}: {
  sessions: Session[];
  incidents: Incident[];
  ouvrirIncident: (id: string) => void;
}) {
  const [reposOuverts, setReposOuverts] = useState(false);

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

  const repos = traites.length + calmes.length;
  const dossiersTraites = traites.flatMap((p) => p.incidents);
  const duJour = dossiersTraites.filter((i) => estAujourdhui(dateTraitement(i))).length;
  const nTraites = duJour || dossiersTraites.length;
  const sousRepos =
    nTraites > 0
      ? `dont ${nTraites} dossier${nTraites > 1 ? "s" : ""} traité${nTraites > 1 ? "s" : ""}${duJour ? " aujourd'hui" : ""}`
      : null;

  return (
    <div className="postes" role="table" aria-label="Postes des salariés">
      {actifs.length === 0 && (
        <p className="postes-vide" role="status">
          Rien à traiter sur les postes
        </p>
      )}
      {actifs.length > 0 && <EntetePostes />}
      {actifs.map((p) => (
        <LignePoste key={p.cle} p={p} ton="actif" ouvrirIncident={ouvrirIncident} />
      ))}
      {repos > 0 && (
        <div className="postes-calmes" role="rowgroup">
          <div role="row">
            <button
              type="button"
              className={`postes-calmes-btn ${reposOuverts ? "ouvert" : ""}`}
              aria-expanded={reposOuverts}
              aria-controls="postes-calmes-liste"
              onClick={() => setReposOuverts((v) => !v)}
            >
              <span className="postes-calmes-lib">
                {repos} poste{repos > 1 ? "s" : ""} sans rien à traiter
                {sousRepos && <span className="postes-calmes-sous">{sousRepos}</span>}
              </span>
              <span className="postes-chevron" aria-hidden="true" />
            </button>
          </div>
          <Depliant ouvert={reposOuverts} id="postes-calmes-liste">
            {actifs.length === 0 && <EntetePostes />}
            {traites.map((p) => (
              <LignePoste key={p.cle} p={p} ton="traite" ouvrirIncident={ouvrirIncident} />
            ))}
            {calmes.map((p) => (
              <LignePoste key={p.cle} p={p} ton="calme" ouvrirIncident={ouvrirIncident} />
            ))}
          </Depliant>
        </div>
      )}
    </div>
  );
}

function EntetePostes() {
  return (
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
