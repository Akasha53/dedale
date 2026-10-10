import type { Classement, Droit, Etat, TypeIncident } from "../types";

// Libellé et icône clairs par type d'incident. Les types internes V2
// (outil/MCP piégé, droits, appel, chatbot, inter-agent, mémoire) ont leur entrée ; un type inconnu
// retombe sur un libellé générique (dégradé propre).
const TYPE_INCIDENT: Record<string, { lib: string; pic: string }> = {
  interne_canari: { lib: "Canari déclenché", pic: "✉" },
  interne_outil_mcp: { lib: "Outil / MCP piégé", pic: "⚙" },
  interne_droits: { lib: "Droits trop larges", pic: "🔑" },
  interne_appel: { lib: "Appel piégé", pic: "☎" },
  interne_chatbot: { lib: "Chatbot détourné", pic: "💬" },
  interne_inter_agent: { lib: "Usurpation d'agent", pic: "⇄" },
  interne_memoire: { lib: "Mémoire empoisonnée", pic: "❖" },
  externe_agent_ia: { lib: "Agent externe", pic: "☍" },
};

export function libelleType(type?: TypeIncident): string {
  if (!type) return "Incident";
  return TYPE_INCIDENT[type]?.lib ?? type.replace(/_/g, " ");
}

export function BadgeTypeIncident({ type }: { type?: TypeIncident }) {
  if (!type) return null;
  const t = TYPE_INCIDENT[type];
  const cls = t ? type : "generique";
  return (
    <span className={`type-inc ${cls}`} title={type}>
      <span className="pic">{t?.pic ?? "⬡"}</span>
      {libelleType(type)}
    </span>
  );
}

// Normalise un droit (chaîne « code » ou objet {code, libelle}).
export function codeDroit(d: Droit): string {
  return typeof d === "string" ? d : d.code;
}
export function libDroit(d: Droit): string {
  if (typeof d === "string") return d;
  return d.libelle ? `${d.libelle} (${d.code})` : d.code;
}

export const LIB_CLASSEMENT: Record<Classement, string> = {
  humain: "Humain",
  script: "Script",
  agent_ia: "Agent IA",
  inconnu: "Inconnu",
};

export function BadgeClassement({ c }: { c: Classement }) {
  return (
    <span className={`badge ${c}`}>
      <span className="pt" />
      {LIB_CLASSEMENT[c]}
    </span>
  );
}

const LIB_ETAT: Record<Etat, string> = {
  active: "active",
  suspendue: "suspendue",
  coupee: "coupée",
};

export function BadgeEtat({ e }: { e: Etat }) {
  return <span className={`badge etat ${e}`}>● {LIB_ETAT[e]}</span>;
}

// Normalise un score 0..1 (tolère 0..100) et renvoie un pourcentage entier.
export function pct(score: number): number {
  const v = score > 1 ? score : score * 100;
  return Math.round(Math.min(100, Math.max(0, v)));
}

export function couleurScore(score: number): string {
  const p = pct(score);
  if (p >= 75) return "var(--agent)";
  if (p >= 45) return "var(--script)";
  if (p >= 20) return "var(--inconnu)";
  return "var(--humain)";
}

export function JaugeScore({ score }: { score: number }) {
  const p = pct(score);
  return (
    <div className="score">
      <div className="barre">
        <span style={{ width: `${p}%`, background: couleurScore(score) }} />
      </div>
      <span className="num" style={{ color: couleurScore(score) }}>
        {p}
      </span>
    </div>
  );
}

export function Spinner({ texte = "Chargement…" }: { texte?: string }) {
  return (
    <div className="charge">
      <div className="spinner" />
      {texte}
    </div>
  );
}

export function tempsRelatif(iso?: string): string {
  if (!iso) return "—";
  const d = new Date(iso).getTime();
  if (Number.isNaN(d)) return "—";
  const s = Math.max(0, Math.round((Date.now() - d) / 1000));
  if (s < 5) return "à l'instant";
  if (s < 60) return `il y a ${s} s`;
  const m = Math.round(s / 60);
  if (m < 60) return `il y a ${m} min`;
  const h = Math.round(m / 60);
  return `il y a ${h} h`;
}

export function heure(iso?: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
