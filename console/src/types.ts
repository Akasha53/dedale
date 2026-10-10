// Types consommés par la console. Ils suivent CONTRATS.md ; les champs ajoutés
// par la console (signaux détaillés, chaîne boîte noire, séries de mesures) sont
// notés dans CONTRATS.md, section « Changements demandés », pour que le backend
// (agent A) s'aligne. Tout est rendu tolérant à l'absence d'un champ.

export type Classement = "humain" | "script" | "agent_ia" | "inconnu";
export type Etat = "active" | "suspendue" | "coupee";
// Avenant « humain, le maillon faible » : la source `humain` (le poste du
// salarié) et la source `physique` (accès aux locaux/serveurs) s'ajoutent aux
// deux sources IA. La console tolère une source inconnue.
export type Source = "externe" | "interne" | "humain" | "physique" | (string & {});

// Filtres d'une même console : salariés, agents internes, surface externe.
export type Pilier = "humain" | "interne" | "externe";

// Choix du salarié face à l'avertissement du garde du corps : il annule (bien,
// le geste risqué est arrêté) ou passe outre (incident).
export type ChoixSalarie = "continuer" | "annuler";

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

// Phase d'un maillon de la boîte noire. `avertissement` est le maillon propre
// aux incidents humains : le garde du corps a prévenu le salarié avant le geste.
export type Phase =
  | "entree"
  | "consigne"
  | "outil"
  | "sortie"
  | "riposte"
  | "contexte"
  | "action_risquee"
  | "avertissement"
  | "choix"
  | "consequence"
  | (string & {});

export interface MaillonChaine {
  ordre: number;
  phase: Phase;
  horodatage?: string;
  titre: string;
  detail: string;
  evenement_id?: number;
  leurre_id?: string | null;
  canari_id?: string | null;
  // Pour un maillon `avertissement` : le choix du salarié face à la pop-up.
  choix?: ChoixSalarie;
  techniques?: Technique[];
  risques?: Risque[];
}

// Type d'incident. Les valeurs internes V2 (outil/MCP piégé, droits trop
// larges) s'ajoutent aux canaris existants. La console affiche un libellé et
// une icône par valeur connue, et retombe sur un rendu générique pour toute
// valeur inconnue (dégradé propre tant que le backend n'expose pas V2).
export type TypeIncident =
  // Pilier salariés (avenant « humain, le maillon faible »).
  | "humain_secret"
  | "humain_mail_externe"
  | "humain_upload_ia"
  | "humain_phishing"
  | "humain_intrusion_physique"
  // Pilier agents IA internes.
  | "interne_canari"
  | "interne_outil_mcp"
  | "interne_droits"
  | "interne_appel"
  | "interne_chatbot"
  | "interne_inter_agent"
  | "interne_memoire"
  // Réserve externe.
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
  | "clore"
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
  statut?: "ouvert" | "surveille" | "clos" | "ignore";
  droits?: DroitsAgent; // présent surtout pour type "interne_droits"
  // Incident humain : le geste risqué observé, le texte de l'avertissement
  // affiché au salarié, et son choix. Tous optionnels (dégradé propre tant que
  // le backend ne les renvoie pas) ; à défaut, lus dans le maillon
  // `avertissement` de la chaîne.
  geste?: string;
  avertissement?: string;
  choix?: ChoixSalarie;
  evenements?: Evenement[];
}

export interface Evenement {
  id: number;
  type: string;
  horodatage?: string;
  details: Record<string, unknown>;
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
  taux_detection: number | null; // 0..1, absent sans vérité terrain
  faux_positifs: number | null; // 0..1, absent sans vérité terrain
  temps_detection_s: number | null; // moyenne, secondes
  temps_confinement_s: number | null; // moyenne, secondes
  sessions_total: number;
  agents_detectes: number;
  incidents_ouverts: number;
  incidents_clos: number;
  repartition: Record<Classement, number>;
  serie_detection: PointSerie[];
  gestes_humains?: GestesHumains;
}

// Bloc du pilier salariés dans /api/mesures (toléré absent). « arretes » =
// avertissements annulés, « passes_outre » = avertissements continués.
export interface GestesHumains {
  arretes: number;
  passes_outre: number;
  total: number;
  passes_outre_par_type?: Record<string, number>;
  incidents_humains?: number;
}

// Message du WebSocket /ws
export interface MessageWS {
  type: "evenement" | "session" | "incident";
  donnees: unknown;
}

export type ModeConnexion = "live" | "mock" | "connexion";
export type EtatFlux = "connecte" | "reconnexion" | "absent";
