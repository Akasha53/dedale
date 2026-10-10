// Détail d'une étape de boîte noire, déplié sur place : ce qui s'est passé
// exactement, pourquoi Dédale l'a repéré, ce que ça aurait pu provoquer, puis
// l'heure précise et les références techniques, repliées par défaut.

import { useEffect, useRef, type ReactNode } from "react";
import type { DetailMaillon } from "./boiteNoire";
import { ListeRefs } from "./references";
import { TexteCanary } from "../ui/Canary";

function heureFine(iso?: string): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const hms = d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const date = d.toLocaleDateString("fr-FR", { day: "numeric", month: "long" });
  return `${date}, ${hms},${String(d.getMilliseconds()).padStart(3, "0")}`;
}

// Enveloppe animée : la hauteur suit le contenu (grille 0fr → 1fr). Fermée,
// elle est inerte : ni focus, ni lecteur d'écran.
export function Depliant({ ouvert, id, children }: { ouvert: boolean; id: string; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (ref.current) (ref.current as HTMLDivElement & { inert: boolean }).inert = !ouvert;
  }, [ouvert]);
  return (
    <div className={`depliant ${ouvert ? "ouvert" : ""}`} id={id} ref={ref}>
      <div className="depliant-interieur">{children}</div>
    </div>
  );
}

export function DetailEtape({ detail, horodatage }: { detail: DetailMaillon; horodatage?: string }) {
  const heure = heureFine(horodatage);
  const rien = detail.brut.length === 0 && !detail.pourquoi && !detail.risque;
  return (
    <div className="dp">
      {rien && <p className="dp-texte dp-vide">Pas de détail supplémentaire pour cette étape.</p>}
      {detail.brut.length > 0 && (
        <section className="dp-bloc">
          <h5>Ce qui s'est passé exactement</h5>
          <dl className="dp-brut">
            {detail.brut.map((b, i) => (
              <div key={i} className={b.piege ? "dp-piege" : ""}>
                <dt>{b.lib}</dt>
                <dd className={b.mono ? "mono" : ""}>{b.piege ? <mark className="piege-ligne">{b.valeur}</mark> : b.valeur}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}
      {detail.pourquoi && (
        <section className="dp-bloc">
          <h5>Pourquoi Dédale l'a repéré</h5>
          <p className="dp-texte">
            <TexteCanary texte={detail.pourquoi} />
          </p>
        </section>
      )}
      {detail.risque && (
        <section className="dp-bloc">
          <h5>Si rien ne l'avait arrêté</h5>
          <p className="dp-texte">
            <TexteCanary texte={detail.risque} />
          </p>
        </section>
      )}
      {(heure || detail.refs.length > 0) && (
        <div className="dp-pied">
          {heure && <span className="dp-heure">Heure précise : {heure}</span>}
          {detail.refs.length > 0 && (
            <details className="dp-refs">
              <summary>Références techniques ({detail.refs.length})</summary>
              <ListeRefs refs={detail.refs} />
            </details>
          )}
        </div>
      )}
    </div>
  );
}
