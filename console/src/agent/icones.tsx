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

const TRACES: Record<CleMaillon | "couper" | "reprendre" | "chrono" | "bouclier", JSX.Element> = {
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
