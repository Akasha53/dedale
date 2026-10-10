// Repères OWASP Agentic, MITRE ATLAS et ATT&CK, en badges discrets. Le badge
// porte l'identifiant ; le nom officiel passe en infobulle quand il est sûr.
// Ce sont des repères pour situer le risque, pas une certification.

export type Cadre = "OWASP" | "ATLAS" | "ATT&CK";
export interface Ref {
  id: string; // forme courte : ASI01, AML.T0051, T1566
  cadre: Cadre;
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
  T1048: "Exfiltration Over Alternative Protocol",
  T1119: "Automated Collection",
  T1200: "Hardware Additions",
  T1552: "Unsecured Credentials",
  T1566: "Phishing",
  T1567: "Exfiltration Over Web Service",
};

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
  const vues = new Set<string>();
  const ordre: Record<Cadre, number> = { OWASP: 0, ATLAS: 1, "ATT&CK": 2 };
  const toutes: Ref[] = [];
  for (const liste of listes)
    for (const r of liste) {
      if (!r || vues.has(r.id)) continue;
      vues.add(r.id);
      toutes.push(r);
    }
  return toutes.sort((a, b) => ordre[a.cadre] - ordre[b.cadre] || a.id.localeCompare(b.id));
}

export function BadgesRefs({ refs, legende }: { refs: Ref[]; legende?: boolean }) {
  if (refs.length === 0) return null;
  return (
    <div className="ag-refs" aria-label="Repères de risque">
      {refs.map((r) => {
        const nom = NOMS[r.id];
        return (
          <span
            key={r.id}
            className={`ag-ref ag-ref-${r.cadre === "OWASP" ? "owasp" : r.cadre === "ATLAS" ? "atlas" : "attack"}`}
            title={`${LIB_CADRE[r.cadre]} ${r.id}${nom ? ` · ${nom}` : ""}`}
          >
            <span className="ag-ref-cadre">{r.cadre === "OWASP" ? "OWASP" : r.cadre}</span>
            {r.id}
          </span>
        );
      })}
      {legende && <span className="ag-refs-note">repères, pas une certification</span>}
    </div>
  );
}
