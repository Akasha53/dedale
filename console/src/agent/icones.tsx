// Pictos fins, tracés à la main (trait 1.4) : pas de bibliothèque d'icônes.
import type { CleMaillon } from "./boiteNoire";

const base = {
  width: 18,
  height: 18,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.4,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

const TRACES: Record<CleMaillon | "couper" | "reprendre" | "chrono" | "bouclier" | "fermer" | "oeil" | "direct" | "incidents" | "mesures" | "entreprise", JSX.Element> = {
  source: (
    <>
      <rect x="3.5" y="5.5" width="17" height="13" rx="2.5" />
      <path d="m4 7 8 6 8-6" />
    </>
  ),
  consigne: (
    <>
      <path d="M12 3.5 21 19.5H3z" />
      <path d="M12 10v4.2M12 16.8v.2" />
    </>
  ),
  intention: (
    <>
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="3.6" />
      <path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3" />
    </>
  ),
  appel: (
    <>
      <path d="m8 8-4.5 4L8 16M16 8l4.5 4-4.5 4" />
      <path d="m13.5 5-3 14" />
    </>
  ),
  decision: (
    <>
      <path d="M12 3 19.5 6v5.5c0 4.4-3.2 8-7.5 9.5-4.3-1.5-7.5-5.1-7.5-9.5V6z" />
      <path d="m9 12 2.2 2.2L15.5 10" />
    </>
  ),
  resultat: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M8 12h8M13 9l3 3-3 3" />
    </>
  ),
  correctif: (
    <>
      <circle cx="8" cy="12" r="3.6" />
      <path d="M11.6 12H20.5M17.5 12v3M20.5 12v2.2" />
    </>
  ),
  fermer: <path d="M6.5 6.5l11 11M17.5 6.5l-11 11" />,
  direct: <path d="M3 12h4l2.5-6 5 12 2.5-6H21" />,
  incidents: (
    <>
      <path d="M4 13.5 6.5 5h11l2.5 8.5V19H4z" />
      <path d="M4 13.5h5l1 2h4l1-2h5" />
    </>
  ),
  mesures: <path d="M5 19V11M12 19V5M19 19v-5" />,
  entreprise: (
    <>
      <path d="M4.5 20V6.5L12 4v16M12 9.5h7.5V20M3 20h18" />
      <path d="M7.5 9v.01M7.5 12.5v.01M7.5 16v.01M15.5 13v.01M15.5 16.5v.01" />
    </>
  ),
  oeil: (
    <>
      <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" />
      <circle cx="12" cy="12" r="2.8" />
    </>
  ),
  couper: (
    <>
      <path d="M12 3.5v8" />
      <path d="M7.2 6.6a7 7 0 1 0 9.6 0" />
    </>
  ),
  reprendre: <path d="M8.5 6v12l9.5-6z" />,
  chrono: (
    <>
      <circle cx="12" cy="13" r="7.5" />
      <path d="M12 9.5V13l2.4 1.6M10 3h4" />
    </>
  ),
  bouclier: <path d="M12 3 19.5 6v5.5c0 4.4-3.2 8-7.5 9.5-4.3-1.5-7.5-5.1-7.5-9.5V6z" />,
};

export function Icone({ nom, taille = 18 }: { nom: keyof typeof TRACES; taille?: number }) {
  return (
    <svg {...base} width={taille} height={taille}>
      {TRACES[nom]}
    </svg>
  );
}
