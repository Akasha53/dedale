import type { Incident } from "../types";
import "./confidentialite.css";

// Besoin d'en connaître (CONTRATS.md) : la console du SOC lit les montants en
// tranches, sans bénéficiaire ni IBAN. Sur un signal de fraude seulement, la
// vue détaillée s'ouvre en clair et la consultation est notée au journal scellé.

interface DetailConfidentiel {
  geste?: string | null;
  montant_eur?: number | null;
  beneficiaire?: string | null;
  iban?: string | null;
  volume?: number | null;
  destination?: string | null;
}

interface Confidentialite {
  niveau: "en_clair" | "minimise";
  signal_fraude?: string | null;
  mention?: string;
  detail?: DetailConfidentiel | null;
}

const EUROS = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });

function morceaux(d: DetailConfidentiel): string[] {
  return [
    typeof d.montant_eur === "number" ? EUROS.format(d.montant_eur) : null,
    typeof d.volume === "number" ? `${d.volume.toLocaleString("fr-FR")} fiches` : null,
    d.beneficiaire ?? d.destination ?? null,
    d.iban ? `IBAN ${d.iban}` : null,
  ].filter((m): m is string => Boolean(m));
}

export function BandeauConfidentialite({ incident }: { incident: Incident }) {
  const c = (incident as Incident & { confidentialite?: Confidentialite }).confidentialite;
  if (!c) return null;
  if (c.niveau === "minimise") {
    return (
      <p className="conf conf-minimise">
        <Cadenas />
        Montants en tranches, bénéficiaire et IBAN masqués. Le responsable du salarié ou la finance voit le
        détail dans l'espace de validation.
      </p>
    );
  }
  const detail = c.detail ? morceaux(c.detail) : [];
  return (
    <div className="conf conf-clair" role="note">
      <span className="conf-point" aria-hidden="true" />
      <div>
        <p className="conf-titre">Détail visible : signal de fraude</p>
        {c.signal_fraude && <p className="conf-raison">{c.signal_fraude}</p>}
        {detail.length > 0 && <p className="conf-detail">{detail.join(" · ")}</p>}
        <p className="conf-note">Cette consultation est notée au journal scellé.</p>
      </div>
    </div>
  );
}

function Cadenas() {
  return (
    <svg className="conf-cadenas" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
      <rect x="3.25" y="7" width="9.5" height="6.75" rx="1.75" fill="none" stroke="currentColor" strokeWidth="1.3" />
      <path d="M5.5 7V5.25a2.5 2.5 0 0 1 5 0V7" fill="none" stroke="currentColor" strokeWidth="1.3" />
    </svg>
  );
}
