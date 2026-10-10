// Repères OWASP Agentic, MITRE ATLAS et ATT&CK. Ils ne s'affichent qu'en bas
// d'une étape dépliée, repliés par défaut, pour qui veut les voir.

export type Cadre = "OWASP" | "ATLAS" | "ATT&CK";
export interface Ref {
  id: string; // forme courte : ASI01, AML.T0051, T1566
  cadre: Cadre;
  // Rapprochement plausible mais pas établi : le backend envoie a_confirmer.
  aConfirmer?: boolean;
  nom?: string; // nom envoyé par le backend, s'il y en a un
}

// Noms officiels (anglais) : OWASP Top 10 for Agentic Applications (2026),
// MITRE ATLAS, MITRE ATT&CK. Un identifiant absent de la table s'affiche seul.
const NOMS: Record<string, string> = {
  ASI01: "Agent Goal Hijack",
  ASI02: "Tool Misuse and Exploitation",
  ASI03: "Identity and Privilege Abuse",
  ASI04: "Agentic Supply Chain Vulnerabilities",
  ASI05: "Unexpected Code Execution",
  ASI06: "Memory and Context Poisoning",
  ASI07: "Insecure Inter-Agent Communication",
  ASI08: "Cascading Failures",
  ASI09: "Human-Agent Trust Exploitation",
  ASI10: "Rogue Agents",
  "AML.T0051": "LLM Prompt Injection",
  "AML.T0054": "LLM Jailbreak",
  "AML.T0057": "LLM Data Leakage",
  T1041: "Exfiltration Over C2 Channel",
  T1119: "Automated Collection",
  T1200: "Hardware Additions",
  T1552: "Unsecured Credentials",
  T1566: "Phishing",
  T1567: "Exfiltration Over Web Service",
};

// Noms français des techniques ATT&CK que le backend pose sur la chaîne d'un
// agent interne (CONTRATS.md). Le backend les envoie en anglais ; la console
// affiche ces noms-ci.
const NOMS_ATTACK_FR: Record<string, string> = {
  T1078: "Comptes valides",
  T1555: "Identifiants dans les coffres à mots de passe",
  T1657: "Vol financier",
  T1195: "Compromission de la chaîne d'approvisionnement",
  T1048: "Exfiltration par un autre protocole",
};

// Nom affiché d'une technique : le nom français s'il est dans la table, sinon
// celui reçu du backend.
export function nomTechnique(id: string, nom?: string): string | undefined {
  return NOMS_ATTACK_FR[id] ?? nom;
}

const LIB_CADRE: Record<Cadre, string> = {
  OWASP: "OWASP Agentic",
  ATLAS: "MITRE ATLAS",
  "ATT&CK": "MITRE ATT&CK",
};

// Normalise une référence venue du backend (« OWASP ASI01 », « AML.T0051 »,
// « T1566 ») ou d'un objet {id, cadre}.
export function lireRef(brut: string, cadre?: string): Ref | null {
  const id = brut.trim().replace(/^OWASP\s+/i, "").toUpperCase();
  if (!id) return null;
  if (/^ASI\d{2}$/.test(id)) return { id, cadre: "OWASP" };
  if (/^AML\.T\d{4}/.test(id)) return { id, cadre: "ATLAS" };
  if (/^T\d{4}/.test(id)) return { id, cadre: cadre === "ATLAS" ? "ATLAS" : "ATT&CK" };
  if (/^LLM\d{2}$/.test(id)) return { id: `LLM${id.slice(3)}`, cadre: "OWASP" };
  return null;
}

export function fusionnerRefs(...listes: (Ref | null | undefined)[][]): Ref[] {
  const vues = new Map<string, Ref>();
  const ordre: Record<Cadre, number> = { OWASP: 0, ATLAS: 1, "ATT&CK": 2 };
  for (const liste of listes)
    for (const r of liste) {
      if (!r) continue;
      const deja = vues.get(r.id);
      // Une même technique peut venir du leurre et de la chaîne du backend :
      // on garde la première, avec la réserve « à confirmer » si l'une la porte.
      if (!deja) vues.set(r.id, r);
      else if (r.aConfirmer && !deja.aConfirmer) vues.set(r.id, { ...deja, aConfirmer: true });
    }
  return [...vues.values()].sort((a, b) => ordre[a.cadre] - ordre[b.cadre] || a.id.localeCompare(b.id));
}

export function nomRef(r: Ref): string | undefined {
  return NOMS_ATTACK_FR[r.id] ?? NOMS[r.id] ?? r.nom;
}

export function ListeRefs({ refs }: { refs: Ref[] }) {
  if (refs.length === 0) return null;
  return (
    <ul className="refs-liste">
      {refs.map((r) => (
        <li key={r.id}>
          <span className="refs-cadre">{LIB_CADRE[r.cadre]}</span>
          <span className="refs-id">{r.id}</span>
          {nomRef(r) && <span className="refs-nom">{nomRef(r)}</span>}
          {r.aConfirmer && <span className="refs-doute">à confirmer</span>}
        </li>
      ))}
    </ul>
  );
}
