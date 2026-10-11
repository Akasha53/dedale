// Espace de validation métier : ce que lit et envoie la page /validation.
// Contrat : CONTRATS.md, avenant « Besoin d'en connaître ». Les routes
// /api/validation/ n'admettent que l'identité validateur ; en dev, le proxy de
// Vite pose son jeton, jamais le JavaScript servi.

export type Geste = "virement" | "export_clients" | "autre";
// « retenu_soc » : signes de fraude, le geste est retenu par l'équipe sécurité et ne s'accorde pas ici.
export type Statut = "en_attente" | "retenu_soc" | "accorde" | "refuse";
export type Qualite = "responsable" | "finance";

export interface FicheGeste {
  id: string;
  geste: Geste;
  titre: string;
  montant_eur: number | null;
  lecture_du_montant?: string | null;
  volume: number | null;
  destination: string | null;
  beneficiaire: {
    nom: string | null;
    connu: boolean;
    nature?: string | null;
    objet?: string | null;
    montant_habituel_eur?: number | null;
  } | null;
  iban: string | null;
  rib: "habituel" | "nouveau" | "non_precise" | null;
  demande: string | null;
  demandeur: { nom: string | null; service: string | null };
  motif: string | null;
  raisons: string[];
  demande_le: string | null;
  statut: Statut;
  decision: {
    decision: "accorde" | "refuse";
    validateur: string | null;
    motif: string | null;
    horodatage: string | null;
  } | null;
}

export interface FileValidation {
  gestes: FicheGeste[];
  traites: FicheGeste[];
  total: number;
}

export class ErreurApi extends Error {
  constructor(public statut: number, message: string) {
    super(message);
  }
}

async function lire<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let detail = `Erreur ${r.status}`;
    try {
      const corps = await r.json();
      if (typeof corps?.detail === "string") detail = corps.detail;
    } catch {
      // corps illisible : le code suffit
    }
    throw new ErreurApi(r.status, detail);
  }
  return (await r.json()) as T;
}

export async function chargerFile(signal?: AbortSignal): Promise<FileValidation> {
  return lire<FileValidation>(await fetch("/api/validation/file", { signal, credentials: "same-origin" }));
}

export async function decider(
  id: string,
  decision: "accorder" | "refuser",
  motif: string,
  validateur: string,
  qualite: Qualite
): Promise<FicheGeste> {
  const r = await fetch(`/api/validation/gestes/${encodeURIComponent(id)}/decision`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, motif, validateur, qualite }),
  });
  return lire<FicheGeste>(r);
}

// ---------- mise en forme ----------

const EUROS = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });
const EUROS_RONDS = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
const ENTIERS = new Intl.NumberFormat("fr-FR");

export function euros(v: number | null | undefined, ronds = false): string {
  if (typeof v !== "number") return "montant illisible";
  return (ronds ? EUROS_RONDS : EUROS).format(v);
}

export function entier(v: number | null | undefined): string {
  return typeof v === "number" ? ENTIERS.format(v) : "nombre illisible";
}

export function heure(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
}

export function jourEtHeure(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const aujourdhui = new Date().toDateString() === d.toDateString();
  const h = heure(iso);
  return aujourdhui ? `aujourd'hui à ${h}` : `le ${d.toLocaleDateString("fr-FR", { day: "numeric", month: "short" })} à ${h}`;
}

// « Virement · 3 480 € », « Export · 12 400 fiches »
export function resume(f: FicheGeste): string {
  if (f.geste === "virement") return `Virement · ${euros(f.montant_eur, true)}`;
  if (f.geste === "export_clients") return `Export · ${entier(f.volume)} fiches`;
  return f.titre;
}

export function contrepartie(f: FicheGeste): string {
  if (f.geste === "virement") return f.beneficiaire?.nom ?? "bénéficiaire non lu";
  if (f.geste === "export_clients") return f.destination ?? "destination non lue";
  return "";
}

export function personne(f: FicheGeste): string {
  const { nom, service } = f.demandeur ?? {};
  if (nom && service) return `${nom} · ${service}`;
  return nom ?? service ?? "poste hors annuaire";
}
