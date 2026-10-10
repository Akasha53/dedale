import type {
  Classement,
  ChoixSalarie,
  Droit,
  Etat,
  Pilier,
  Source,
  TypeIncident,
} from "../types";

// Libellé court par type d'incident. Un type inconnu retombe sur un libellé
// générique.
const TYPE_INCIDENT: Record<string, { lib: string }> = {
  humain_secret: { lib: "Clé secrète exposée" },
  humain_mail_externe: { lib: "Envoi vers l'extérieur" },
  humain_upload_ia: { lib: "Fichier vers une IA" },
  humain_phishing: { lib: "Lien piégé" },
  interne_canari: { lib: "Instruction cachée" },
  interne_outil_mcp: { lib: "Faux outil" },
  interne_droits: { lib: "Hors de sa tâche" },
  interne_appel: { lib: "Appel piégé" },
  interne_chatbot: { lib: "Message piégé" },
  interne_inter_agent: { lib: "Faux collègue" },
  interne_memoire: { lib: "Fausse mémoire" },
  interne_desarme: { lib: "Désarmé avant lecture" },
  interne_envoi_externe: { lib: "Envoi vers l'extérieur" },
  interne_politique: { lib: "Règle du SOC" },
  interne_anomalie: { lib: "Comportement inhabituel" },
  humain_signalement: { lib: "Signalement" },
};

// Les deux piliers, dans l'ordre d'affichage : les agents IA d'abord (le
// produit principal), puis les salariés.
export const PILIERS: { id: Pilier; lib: string; sources: Source[] }[] = [
  { id: "interne", lib: "Agents IA", sources: ["interne"] },
  { id: "humain", lib: "Salariés", sources: ["humain"] },
];

export function pilierDeSource(source?: Source): Pilier {
  if (source === "interne") return "interne";
  return "humain"; // humain, physique, ou inconnu : rattachés aux salariés
}

// La surface externe reste dans le backend ; la console ne l'affiche ni ne la
// compte (sessions, incidents, leurres L-xxxx).
export function horsExterne(x: { source?: Source }): boolean {
  return x.source !== "externe";
}

// Ce que la console affiche : agents IA et salariés. La surface externe et le
// volet physique (abandonné, feuille de route) restent hors de l'écran.
export function visibleConsole(x: { source?: Source; type?: string }): boolean {
  return x.source !== "externe" && x.source !== "physique" && x.type !== "humain_intrusion_physique";
}

export function appartientPilier(source: Source | undefined, pilier: Pilier): boolean {
  return pilierDeSource(source) === pilier;
}

// Contrôle segmenté des piliers, partagé par le temps réel et les incidents.
// Le nombre d'un onglet est celui des dossiers à traiter du pilier : le même que
// le badge de la barre latérale et les compteurs (ui/compteurs.ts).
export function SegmentsPiliers({
  pilier,
  setPilier,
  comptes,
  titreCompte = "à traiter",
}: {
  pilier: Pilier;
  setPilier: (p: Pilier) => void;
  comptes: Record<Pilier, number>;
  titreCompte?: string;
}) {
  return (
    <div className="segments" role="tablist">
      {PILIERS.map((p) => {
        const n = comptes[p.id] ?? 0;
        return (
          <button
            key={p.id}
            role="tab"
            data-pilier={p.id}
            aria-selected={pilier === p.id}
            className={pilier === p.id ? "actif" : ""}
            onClick={() => setPilier(p.id)}
          >
            {p.lib}
            {n > 0 && (
              <span className="pastille-compte a-traiter" title={`${n} ${titreCompte}`}>
                {n}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

// Verdict d'un geste risqué : le salarié a annulé (protégé) ou est passé outre
// (incident). Rien à afficher si le choix est inconnu (dégradé propre).
export function BadgeChoixSalarie({ choix }: { choix?: ChoixSalarie }) {
  if (!choix) return null;
  const annule = choix === "annuler";
  return (
    <span className={`badge-choix ${annule ? "bien" : "outre"}`}>
      {annule ? "Annulé à temps" : "Continué malgré l'alerte"}
    </span>
  );
}

export function libelleType(type?: TypeIncident): string {
  if (!type) return "Incident";
  return TYPE_INCIDENT[type]?.lib ?? type.replace(/_/g, " ");
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
