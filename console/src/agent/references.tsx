// Repères OWASP Agentic, MITRE ATLAS et ATT&CK, en badges discrets. Le badge
// porte l'identifiant ; le nom officiel passe en infobulle quand il est sûr.
// Ce sont des repères pour situer le risque, pas une certification.

export type Cadre = "OWASP" | "ATLAS" | "ATT&CK";
export interface Ref {
  id: string; // forme courte : ASI01, AML.T0051, T1566
  cadre: Cadre;
  // Rapprochement plausible mais pas établi : le backend envoie a_confirmer.
  aConfirmer?: boolean;
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

export function BadgesRefs({ refs, legende }: { refs: Ref[]; legende?: boolean }) {
  if (refs.length === 0) return null;
  return (
    <div className="ag-refs" aria-label="Repères de risque">
      {refs.map((r) => {
        const nom = NOMS_ATTACK_FR[r.id] ?? NOMS[r.id];
        return (
          <span
            key={r.id}
            className={`ag-ref ag-ref-${r.cadre === "OWASP" ? "owasp" : r.cadre === "ATLAS" ? "atlas" : "attack"}${r.aConfirmer ? " a-confirmer" : ""}`}
            title={`${LIB_CADRE[r.cadre]} ${r.id}${nom ? ` · ${nom}` : ""}${r.aConfirmer ? " · rapprochement à confirmer" : ""}`}
          >
            <span className="ag-ref-cadre">{r.cadre === "OWASP" ? "OWASP" : r.cadre}</span>
            {r.id}
            {r.aConfirmer && <span className="ag-ref-doute">à confirmer</span>}
          </span>
        );
      })}
      {legende && <span className="ag-refs-note">repères, pas une certification</span>}
    </div>
  );
}
