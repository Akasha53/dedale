// Types consommés par la console. Ils suivent CONTRATS.md ; les champs ajoutés
// par la console (signaux détaillés, chaîne boîte noire, séries de mesures) sont
// notés dans CONTRATS.md, section « Changements demandés », pour que le backend
// (agent A) s'aligne. Tout est rendu tolérant à l'absence d'un champ.

export type Classement = "humain" | "script" | "agent_ia" | "inconnu";
export type Etat = "active" | "suspendue" | "coupee";
export type Source = "externe" | "interne";

export interface Signal {
  code: string; // ex. "consigne_cachee"
  libelle: string; // explication en clair
  poids: number; // contribution au score, -1..1
  valeur?: string; // mesure observée, ex. "1,7 s"
}

export interface Session {
  id: string;
  classement: Classement;
  score: number; // 0..1 (toléré 0..100)
  etat: Etat;
  source: Source;
  signaux: Signal[];
  leurres_touches: number;
  premiere_vue?: string; // ISO
  derniere_vue?: string; // ISO
  ip?: string | null;
  user_agent?: string | null;
  droits?: DroitsAgent; // optionnel : droits de l'agent interne de la session
}

export type Cadre = "ATLAS" | "ATT&CK";
export interface Technique {
  id: string; // ex. "AML.T0051"
  nom: string;
  cadre: Cadre;
}
export interface Risque {
  id: string; // OWASP Agentic, ex. "ASI01"
  nom: string;
}

export type Phase = "entree" | "consigne" | "outil" | "sortie" | "riposte";

export interface MaillonChaine {
  ordre: number;
  phase: Phase;
  horodatage?: string;
  titre: string;
  detail: string;
  leurre_id?: string | null;
  canari_id?: string | null;
  techniques?: Technique[];
  risques?: Risque[];
}

// Type d'incident. Les valeurs internes V2 (outil/MCP piégé, droits trop
// larges) s'ajoutent aux canaris existants. La console affiche un libellé et
// une icône par valeur connue, et retombe sur un rendu générique pour toute
// valeur inconnue (dégradé propre tant que le backend n'expose pas V2).
export type TypeIncident =
  | "interne_canari"
  | "interne_outil_mcp"
  | "interne_droits"
  | "externe_agent_ia"
  | (string & {}); // tolère une valeur non prévue

// Droits d'un agent interne : ce qu'on lui a accordé, ce qu'il a réellement
// utilisé, et ce dont sa tâche avait besoin. L'écart accordé/nécessaire porte
// l'argument « cet agent avait accès à bien plus que sa tâche ». Chaque entrée
// est un code (ex. "clients:export") ou un objet {code, libelle}.
export type Droit = string | { code: string; libelle?: string };

export interface DroitsAgent {
  accordes: Droit[];
  utilises?: Droit[];
  necessaires: Droit[];
}

export type DecisionAction =
  | "valider_riposte"
  | "couper"
  | "reprendre"
  | "ignorer";

export interface Decision {
  action: DecisionAction;
  analyste: string;
  horodatage?: string;
}

export type Gravite = "faible" | "moyenne" | "haute" | "critique";

export interface Incident {
  id: string;
  session_id: string;
  source: Source;
  classement: Classement;
  score: number;
  etat: Etat;
  type?: TypeIncident; // ex. "interne_canari", "interne_outil_mcp", "interne_droits"
  titre: string;
  gravite: Gravite;
  ouvert_le?: string; // ISO
  resume: string;
  chaine: MaillonChaine[];
  decisions: Decision[];
  droits?: DroitsAgent; // présent surtout pour type "interne_droits"
}

export interface Leurre {
  id: string; // L-xxxx (externe) ou C-xxxx (canari interne)
  source: Source;
  surface: string;
  nature: string;
  emplacement: string;
  description: string;
  risques: string[]; // ex. ["OWASP ASI01"]
  techniques: string[]; // ex. ["AML.T0051"]
  humain_visible: boolean;
  touches: number;
  derniere_touche?: string | null;
}

export interface PointSerie {
  t: string; // libellé ou ISO
  valeur: number;
}

export interface Mesures {
  taux_detection: number; // 0..1
  faux_positifs: number; // 0..1
  temps_detection_s: number; // médiane, secondes
  temps_confinement_s: number; // médiane, secondes
  sessions_total: number;
  agents_detectes: number;
  incidents_ouverts: number;
  incidents_clos: number;
  repartition: Record<Classement, number>;
  serie_detection: PointSerie[];
}

// Message du WebSocket /ws
export interface MessageWS {
  type: "evenement" | "session" | "incident";
  donnees: unknown;
}

export type ModeConnexion = "live" | "mock" | "connexion";
export type EtatFlux = "connecte" | "reconnexion" | "absent";
