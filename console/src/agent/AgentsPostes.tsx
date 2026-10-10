// Agents IA trouvés sur les postes des salariés (app Mac) : les serveurs MCP de
// Claude, Cursor, VS Code… avec leurs outils et leurs droits à risque. Ils ne
// font pas partie des agents d'Orbis Pay : on les range à part, par poste.

import { useMemo } from "react";
import type { AgentInventaire } from "../types";
import { tempsRelatif } from "../ui/primitives";

const TYPES: Record<string, string> = {
  fichiers: "fichiers",
  shell: "terminal",
  mail: "mail",
  navigateur: "navigateur",
  reseau: "réseau",
  autre: "autre",
};

const DROITS: Record<string, string> = {
  shell: "lance des commandes",
  disque_entier: "voit tout le disque",
  mail: "lit et envoie des mails",
};

// « poste-mac-1a2b3c4d » devient « Mac 1a2b3c4d » : un identifiant tiré au
// hasard, jamais le nom du Mac ni celui du salarié.
function nomPoste(id?: string): string {
  if (!id) return "Poste inconnu";
  const m = /^poste-(mac|win|pc)-([a-z0-9]+)$/i.exec(id);
  return m ? `${m[1] === "mac" ? "Mac" : "PC"} ${m[2]}` : id;
}

export function AgentsPostes({ inventaire }: { inventaire: AgentInventaire[] }) {
  const postes = useMemo(() => {
    const parPoste = new Map<string, AgentInventaire[]>();
    for (const a of inventaire.filter((x) => x.contexte === "poste")) {
      const cle = a.poste ?? "?";
      parPoste.set(cle, [...(parPoste.get(cle) ?? []), a]);
    }
    return [...parPoste.entries()].map(([poste, agents]) => ({
      poste,
      agents: [...agents].sort((x, y) => y.risque.score - x.risque.score),
      risques: agents.filter((a) => (a.droits_risques ?? []).length > 0).length,
      demo: agents.some((a) => a.source_config === "demo"),
      vu: agents.map((a) => a.derniere_activite).filter(Boolean).sort().pop() ?? null,
    }));
  }, [inventaire]);

  if (postes.length === 0) return null;

  return (
    <section className="panneau" aria-labelledby="postes-ia-titre">
      <div className="titre">
        <span id="postes-ia-titre">Agents IA trouvés sur les postes</span>
        <span className="droite">hors des agents d'Orbis Pay, déclarés par l'app du poste</span>
      </div>
      <div className="corps postes-ia">
        {postes.map((p) => (
          <div key={p.poste} className="poste-ia">
            <p className="poste-ia-tete">
              <strong>{nomPoste(p.poste)}</strong>
              <span className="inv-doux">
                {" "}
                · {p.agents.length} serveur{p.agents.length > 1 ? "s" : ""} MCP
                {p.risques > 0 ? `, dont ${p.risques} avec des droits à risque` : ""}
                {p.demo ? " · configuration de démonstration" : ""}
                {p.vu ? ` · ${tempsRelatif(p.vu)}` : ""}
              </span>
            </p>
            <ul className="poste-ia-liste">
              {p.agents.map((a) => (
                <li key={a.id} className="poste-ia-ligne">
                  <span className="poste-ia-nom">
                    {a.serveur ?? a.nom}
                    <span className="inv-doux"> · {a.client ?? "client inconnu"}</span>
                  </span>
                  <span className="poste-ia-types">
                    {(a.types ?? []).map((t) => TYPES[t] ?? t).join(", ") || "type inconnu"}
                    {a.transport === "distant" ? " · serveur distant" : ""}
                  </span>
                  <span className="inv-puces">
                    {(a.droits_risques ?? []).length === 0 ? (
                      <span className="inv-doux">pas de droit à risque</span>
                    ) : (
                      (a.droits_risques ?? []).map((d) => (
                        <span key={d} className="inv-puce">
                          {DROITS[d] ?? d}
                        </span>
                      ))
                    )}
                  </span>
                  <span className={`inv-risque r-${a.risque.niveau === "eleve" ? "eleve" : a.risque.niveau}`}>
                    {a.risque.niveau === "eleve" ? "Risque élevé" : a.risque.niveau === "moyen" ? "Risque moyen" : "Risque faible"}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  );
}
