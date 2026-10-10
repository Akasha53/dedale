// Une seule source pour tous les chiffres de la console : le badge de la barre
// latérale, les onglets Agents IA / Salariés, les compteurs du temps réel et la
// page Mesures. Un même mot donne partout le même nombre.

import type { Activite, AgentInventaire, Incident, Pilier, Session } from "../types";
import { appartientPilier } from "./primitives";
import { attendDecision, estATraiter } from "./mots";

export interface Comptes {
  // Incidents qui demandent un geste de l'analyste (décision ou clôture).
  aTraiter: Record<Pilier, number>;
  // Parmi eux, ceux dont une action attend une décision humaine (orange).
  aDecider: Record<Pilier, number>;
  // Incidents réglés : décidés, clos ou classés.
  regles: Record<Pilier, number>;
  // Agents de l'inventaire (déclarés, plus ceux vus sans déclaration).
  agents: number;
  // Postes de salariés : un pseudonyme compte une fois, quel que soit le canal.
  postes: number;
  // Actions d'agents vues dans le fil, et celles que Dédale a retenues ou refusées.
  actionsVues: number;
  actionsArretees: number;
}

export function clePoste(s: Session): string {
  return s.identite?.pseudonyme ?? s.id;
}

export function compter(
  incidents: Incident[],
  sessions: Session[],
  inventaire: AgentInventaire[],
  activite: Activite[]
): Comptes {
  const zero = (): Record<Pilier, number> => ({ humain: 0, interne: 0 });
  const aTraiter = zero();
  const aDecider = zero();
  const regles = zero();
  for (const i of incidents) {
    const p: Pilier = appartientPilier(i.source, "interne") ? "interne" : "humain";
    if (estATraiter(i)) aTraiter[p] += 1;
    else regles[p] += 1;
    if (attendDecision(i)) aDecider[p] += 1;
  }
  const agentsVus = new Set(
    sessions
      .filter((s) => s.source === "interne" && s.agent && !estAgentDedale(s.agent))
      .map((s) => s.agent as string)
  );
  // Les agents d'Orbis Pay seulement : les serveurs MCP des postes se comptent à part,
  // et l'agent des règles appartient à Dédale.
  const agents = new Set([
    ...inventaire.filter((a) => a.contexte !== "poste" && !estAgentDedale(a.id, a)).map((a) => a.id),
    ...agentsVus,
  ]).size;
  const postes = new Set(sessions.filter((s) => appartientPilier(s.source, "humain")).map(clePoste)).size;
  return {
    aTraiter,
    aDecider,
    regles,
    agents,
    postes,
    actionsVues: activite.length,
    actionsArretees: activite.filter((a) => a.verdict !== "autorise").length,
  };
}

// Agent de Dédale lui-même (l'agent des règles) : le backend le marque `dedale`,
// et son identifiant commence par « dedale- ».
export function estAgentDedale(id: string, a?: Pick<AgentInventaire, "dedale">): boolean {
  return a?.dedale === true || id.startsWith("dedale-");
}
