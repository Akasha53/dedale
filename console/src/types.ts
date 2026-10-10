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

// Les deux piliers de la console : salariés et agents IA internes. La source
// `externe` existe encore côté backend, la console ne l'affiche plus.
export type Pilier = "humain" | "interne";

// Choix du salarié face à l'avertissement du garde du corps : il annule (bien,
// le geste risqué est arrêté) ou passe outre (incident).
export type ChoixSalarie = "continuer" | "annuler";

export interface Signal {
  code: string; // ex. "consigne_cachee"
  libelle: string; // explication en clair
  poids: number; // contribution au score, -1..1
  valeur?: string; // mesure observée, ex. "1,7 s"
  // Le backend envoie aussi les signaux absents (« Aucune consigne cachée suivie ») :
  // `present` dit s'ils ont été observés. `categorie` : ia, automatisation, humain.
  present?: boolean;
  categorie?: string;
}

// Pseudonyme d'un salarié (le nom ne sort de l'API que sur motif).
export interface IdentiteSalarie {
  pseudonyme: string;
  service?: string | null;
  libelle: string;
  connu?: boolean;
  revelations?: { analyste?: string; horodatage?: string; motif?: string }[];
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
  agent?: string | null; // nom de l'agent interne annoncé par la passerelle
  identite?: IdentiteSalarie; // poste d'un salarié : pseudonyme
}

export type Cadre = "ATLAS" | "ATT&CK";
export interface Technique {
  id: string; // ex. "AML.T0051"
  nom: string;
  cadre: Cadre;
  // ATT&CK posé par le backend sur un agent interne : true quand le
  // rapprochement reste à vérifier (CONTRATS.md).
  a_confirmer?: boolean;
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
  // Maillon « source » d'un agent : le contenu lu, en entier et désarmé.
  document_source?: DocumentSource | null;
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
  // Champs tolérés posés par le backend (moindre privilège) : jeton de la
  // tâche, tâche, surplus accordé et tentatives hors du jeton.
  jeton?: string[];
  tache?: string | null;
  surplus?: string[];
  tentatives_hors_scope?: { outil?: string; scope_requis?: string }[];
}

export type DecisionAction =
  | "valider_riposte"
  | "couper"
  | "reprendre"
  | "clore"
  | "ignorer"
  // Geste critique du salarié (quatre yeux) : l'analyste l'accorde ou le refuse.
  | "accorder"
  | "refuser";

// Acte de la console noté au journal scellé : motif d'une décision, identité levée,
// remédiation simulée.
export interface ActeConsole {
  acte: "decision" | "reveler_identite" | "remediation" | (string & {});
  analyste?: string;
  action?: string;
  motif?: string;
  message?: string;
  domaine?: string;
  horodatage?: string;
}

export interface QuatreYeux {
  demande_id?: string;
  delai_s?: number;
  horodatage?: string;
  issue?: "accorde" | "refuse" | "expire" | null;
}

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
  // Repères de temps lus sur la session liée (GET /api/sessions/{id}) : début,
  // détection (classement agent IA ou canari) et confinement (coupure). Tous
  // optionnels : le chrono se replie sur la chaîne et les décisions.
  temps_session?: TempsSession;
  decide_a?: string | null;
  // Correctif en un clic : droits en trop que l'analyste peut retirer à
  // l'agent, et retraits déjà faits depuis cet incident.
  droits_retirables?: { code: string; libelle?: string }[];
  correctifs?: { code: string; libelle?: string; analyste?: string; horodatage?: string }[];
  // Contenu lu par l'agent (mail, document, description d'outil), quand le
  // backend le transmet. Sinon la console prend sa copie de démonstration.
  source_lue?: SourceLue | null;
  journal_console?: ActeConsole[];
  // Dossier salarié : pseudonyme, contexte du geste (« mail reçu », « navigation »,
  // « signalement »), demande de quatre yeux.
  identite?: IdentiteSalarie;
  contexte_humain?: string | null;
  quatre_yeux?: QuatreYeux | null;
}

// Inventaire des agents déclarés (GET /api/agents, champ `inventaire`).
export interface RaisonRisque {
  code: string;
  points: number;
  texte: string;
  references?: string[];
}
export interface ResistanceAgent {
  mesure?: boolean;
  campagne?: string;
  date?: string;
  score?: number | null;
  essais?: number;
  suivis?: number;
  bloques?: number;
  ignores?: number;
  trafic?: string;
}
export interface AgentInventaire {
  id: string;
  nom: string;
  libelle?: string;
  role?: string;
  service?: string | null;
  proprietaire?: string | null;
  declare?: boolean;
  outils: { nom: string; droit?: string | null; libelle?: string; sortant?: boolean }[];
  droits: {
    accordes: { code: string; libelle?: string }[];
    utilises: string[];
    necessaires: { code: string; libelle?: string }[];
    surplus: string[];
    inutilises?: string[];
    retires?: string[];
  };
  derniere_activite?: string | null;
  sessions: number;
  appels: number;
  resistance?: ResistanceAgent | null;
  incidents: { total: number; ouverts: number; recents_24h: number; ids: string[] };
  risque: { niveau: "faible" | "moyen" | "eleve"; score: number; raisons: RaisonRisque[]; explication?: string };
  // Serveur MCP trouvé sur le poste d'un salarié (app Mac) : `contexte: "poste"`.
  contexte?: "poste" | (string & {});
  poste?: string;
  client?: string;
  serveur?: string;
  types?: string[];
  droits_risques?: string[];
  transport?: "local" | "distant" | (string & {});
  source_config?: "demo" | "reel" | (string & {});
}

// Pré-tri du relecteur IA (GET /api/incidents/{id}/tri).
export interface PreTri {
  incident_id: string;
  statut?: "pret" | "en_cours" | (string & {});
  priorite?: "haute" | "normale" | "basse" | (string & {});
  decision_proposee?: string;
  motif?: string;
  motif_soc?: string;
  confiance?: number;
  doute?: boolean;
  a_regarder?: boolean;
  tranche_par?: string;
  duree_ms?: number;
}

// Règles écrites en français par le SOC (GET/POST /api/politiques).
export interface Politique {
  id: string;
  numero: number;
  texte: string;
  enonce?: string;
  active?: boolean;
  creee_a?: string;
  par?: string;
  declenchements?: number;
  dernier_declenchement?: string | null;
  agent?: string;
  effet?: string;
}
export interface AnalysePolitique {
  phrase: string;
  comprise: boolean;
  texte: string;
  regle: Record<string, unknown> | null;
  manques?: string[];
}

// Intégrité du journal d'un incident (GET /api/incidents/{id}/verification).
export interface Verification {
  statut: "intacte" | "alteree" | "anterieure_au_scellement" | "non_persiste" | (string & {});
  verdict: string;
  raison?: string | null;
  sceau?: string | null;
  verifie_a?: string;
}

export interface RevelationIdentite {
  pseudonyme: string;
  service?: string | null;
  nom?: string | null;
  poste?: string | null;
  message?: string;
  horodatage?: string;
}

export type ActionRemediation = "reinitialiser_mot_de_passe" | "fermer_sessions" | "bloquer_domaine";
export interface Remediation {
  action: ActionRemediation;
  message: string;
  domaine?: string | null;
  horodatage?: string;
}

// Virement demandé par un agent (details.virement d'un appel de paiement).
export interface Virement {
  montant: number;
  devise?: string;
  beneficiaire?: string;
  iban_masque?: string | null;
  complete_par_demo?: boolean;
}

// Document source tel que le backend l'envoie (maillon source de la chaîne,
// ou GET /api/incidents/{id}/source) : désarmé, partie piégée repérée.
export interface DocumentSource {
  type?: "mail" | "document" | "appel" | "memoire" | "outil" | (string & {});
  id?: string;
  titre?: string;
  expediteur?: string;
  destinataire?: string;
  date?: string;
  origine?: string;
  canari_id?: string | null;
  empreinte?: string;
  corps?: string;
  segments?: { texte: string; piege?: boolean }[];
  piege?: { debut: number; fin: number }[];
  texte_piege?: string;
  instruction_cachee?: boolean;
  desarme?: boolean;
  maillon?: number;
  evenement_id?: number;
  horodatage?: string;
}

// Ce que l'agent a lu, affiché en entier dans le panneau « Voir le mail ».
// `corps` est découpé en morceaux ; `piege: true` marque la partie piégée.
export interface SourceLue {
  genre: "mail" | "document" | "outil";
  titre: string;
  de?: string;
  a?: string;
  date?: string;
  morceaux: { texte: string; piege?: boolean }[];
  note?: string;
}

// Copilote SOC : GET /api/incidents/{id}/synthese (CONTRATS.md).
export interface PhraseSynthese {
  texte: string;
  maillons?: number[];
}
export interface RaisonConfiance {
  code: string;
  effet: number;
  texte: string;
}
export interface Synthese {
  incident_id: string;
  phrases: PhraseSynthese[];
  confiance?: {
    score: number;
    niveau?: "elevee" | "moyenne" | "faible" | string;
    raisons?: RaisonConfiance[];
    manquants?: RaisonConfiance[];
  } | null;
  decision_recommandee?: {
    action: DecisionAction | string;
    justification?: string;
    rappel?: string;
    deja_appliquee?: boolean;
    dossier_ferme?: boolean;
  } | null;
  correctif_suggere?: { droit: string; libelle?: string; texte?: string } | null;
}

// Fil des agents : GET /api/activite et messages WS `activite`.
export type VerdictActivite = "autorise" | "retenu" | "refuse";
export interface Activite {
  id: number | string;
  heure: string;
  session_id?: string;
  agent?: string | null;
  outil: string;
  verdict: VerdictActivite;
  raison?: string;
  droit?: string | null;
  etape?: "appel" | "issue" | string;
  incident_id?: string | null;
}

// Réponse de POST /api/incidents/{id}/retirer-droit.
export interface RetraitDroit {
  incident_id: string;
  droit: string;
  libelle?: string;
  message?: string;
  incident?: Incident;
}

export interface TempsSession {
  premiere_vue?: string | null;
  derniere_vue?: string | null;
  detecte_a?: string | null;
  confine_a?: string | null;
}

export interface Evenement {
  id: number;
  type: string;
  horodatage?: string;
  details: Record<string, unknown>;
  // Champs du journal backend, lus par la boîte noire de l'agent.
  source?: string;
  surface?: string;
  outil?: string | null;
  leurre_id?: string | null;
  leurre_nature?: string | null;
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
  // Médiane et moyenne en millisecondes, avec le nombre de mesures.
  temps_detection?: DureeMesuree;
  temps_confinement?: DureeMesuree;
  matrice?: { vrais_positifs: number; faux_positifs: number; vrais_negatifs: number; faux_negatifs: number };
  sessions_sans_verite_terrain?: number;
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
export interface DureeMesuree {
  mediane_ms: number | null;
  moyenne_ms: number | null;
  echantillons: number;
}

export interface GestesHumains {
  arretes: number;
  passes_outre: number;
  total: number;
  signalements?: number;
  passes_outre_par_type?: Record<string, number>;
  incidents_humains?: number;
}

// Message du WebSocket /ws
export interface MessageWS {
  type: "evenement" | "session" | "incident" | "activite";
  donnees: unknown;
}

export type ModeConnexion = "live" | "mock" | "connexion";
export type EtatFlux = "connecte" | "reconnexion" | "absent";
