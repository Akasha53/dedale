// Les postes des salariés, sous pseudonyme. Pas de score : Dédale prévient un
// salarié, il ne le note pas. Un poste compte une fois, qu'il remonte par son
// poste, sa boîte mail ou son navigateur.

import { useMemo } from "react";
import type { Incident, Session } from "../types";
import { clePoste } from "../ui/compteurs";
import { estATraiter, titreIncident } from "../ui/mots";
import { appartientPilier, tempsRelatif } from "../ui/primitives";

function canal(id: string): string {
  if (id.startsWith("mail-")) return "boîte mail";
  if (id.startsWith("navigateur-")) return "navigateur";
  if (id.includes("signalement")) return "signalement";
  return "poste";
}

interface Poste {
  cle: string;
  libelle: string;
  canaux: string[];
  derniere?: string;
  incidents: Incident[];
  aTraiter?: Incident;
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
  const postes = useMemo<Poste[]>(() => {
    const parCle = new Map<string, Poste>();
    for (const s of sessions.filter((x) => appartientPilier(x.source, "humain"))) {
      const cle = clePoste(s);
      const p = parCle.get(cle) ?? {
        cle,
        libelle: s.identite?.libelle ?? "Salarié",
        canaux: [],
        incidents: [],
      };
      const c = canal(s.id);
      if (!p.canaux.includes(c)) p.canaux.push(c);
      if (!p.derniere || (s.derniere_vue ?? "") > p.derniere) p.derniere = s.derniere_vue;
      p.incidents.push(...incidents.filter((i) => i.session_id === s.id));
      parCle.set(cle, p);
    }
    const liste = [...parCle.values()].map((p) => {
      p.incidents.sort((a, b) => (b.ouvert_le ?? "").localeCompare(a.ouvert_le ?? ""));
      return { ...p, aTraiter: p.incidents.find(estATraiter) };
    });
    return liste.sort(
      (a, b) => Number(Boolean(b.aTraiter)) - Number(Boolean(a.aTraiter)) || (b.derniere ?? "").localeCompare(a.derniere ?? "")
    );
  }, [sessions, incidents]);

  if (postes.length === 0) return <div className="vide">Aucun poste protégé pour l'instant.</div>;

  return (
    <ul className="postes-liste">
      {postes.map((p) => {
        const inc = p.aTraiter ?? p.incidents[0];
        const n = p.incidents.filter(estATraiter).length;
        return (
          <li key={p.cle} className="poste-ligne">
            <div className="poste-id">
              <span className="nom">{p.libelle}</span>
              <span className="srcv">
                {p.canaux.join(", ")} · vu {tempsRelatif(p.derniere)}
              </span>
            </div>
            <span className={`statut-pill s-${n > 0 ? "attente" : "ok"}`}>
              <span className="pt" />
              {n > 0 ? `${n} dossier${n > 1 ? "s" : ""} à traiter` : "Rien à traiter"}
            </span>
            <span className="poste-dernier">{inc ? titreIncident(inc) : "Aucun geste risqué"}</span>
            {inc ? (
              <button type="button" className="lien-incident" onClick={() => ouvrirIncident(inc.id)}>
                Voir le dossier
              </button>
            ) : (
              <span />
            )}
          </li>
        );
      })}
    </ul>
  );
}
