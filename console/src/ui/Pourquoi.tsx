// « Pourquoi ? » : un clic ouvre l'explication, Échap, la croix ou un clic
// ailleurs la referment et rendent le focus au bouton. Une seule règle de
// couleur : rouge pour un signe fort, gris pour le reste, vert pour ce qui
// rassure. Jamais deux fois la même ligne.

import { useEffect, useId, useRef, useState } from "react";

export type Force = "fort" | "moyen" | "faible" | "rassurant";

export interface LignePourquoi {
  texte: string;
  force: Force;
  points?: number;
}

const LIB_FORCE: Record<Force, string> = {
  fort: "signe fort",
  moyen: "signe moyen",
  faible: "signe faible",
  rassurant: "rassurant",
};

// Ordre d'affichage : le plus inquiétant d'abord, ce qui rassure à la fin.
const RANG: Record<Force, number> = { fort: 0, moyen: 1, faible: 2, rassurant: 3 };

export function dedoublonner(lignes: LignePourquoi[]): LignePourquoi[] {
  const vues = new Map<string, LignePourquoi>();
  for (const l of lignes) {
    const cle = l.texte.trim().toLowerCase();
    const deja = vues.get(cle);
    // À texte égal, on garde le verdict le plus net.
    if (!deja || RANG[l.force] < RANG[deja.force]) vues.set(cle, l);
  }
  return [...vues.values()].sort((a, b) => RANG[a.force] - RANG[b.force] || (b.points ?? 0) - (a.points ?? 0));
}

export function Pourquoi({
  titre,
  intro,
  lignes,
  vide = "Rien de particulier pour l'instant.",
}: {
  titre: string;
  intro?: string;
  lignes: LignePourquoi[];
  vide?: string;
}) {
  const [ouvert, setOuvert] = useState(false);
  const zone = useRef<HTMLDivElement>(null);
  const bouton = useRef<HTMLButtonElement>(null);
  const id = useId();
  const propres = dedoublonner(lignes);

  useEffect(() => {
    if (!ouvert) return;
    const dehors = (e: MouseEvent) => {
      if (zone.current && !zone.current.contains(e.target as Node)) setOuvert(false);
    };
    const echap = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        setOuvert(false);
        bouton.current?.focus();
      }
    };
    document.addEventListener("mousedown", dehors);
    document.addEventListener("keydown", echap);
    return () => {
      document.removeEventListener("mousedown", dehors);
      document.removeEventListener("keydown", echap);
    };
  }, [ouvert]);

  return (
    <div className="sig-wrap" ref={zone}>
      <button
        ref={bouton}
        type="button"
        className={`sig-btn ${ouvert ? "epingle" : ""}`}
        onClick={() => setOuvert((v) => !v)}
        aria-expanded={ouvert}
        aria-controls={id}
      >
        Pourquoi ?
      </button>
      {ouvert && (
        <div className="sig-pop" role="dialog" aria-label={titre} id={id}>
          <div className="sig-tete">
            <h4>{titre}</h4>
            <button
              type="button"
              className="sig-fermer"
              onClick={() => {
                setOuvert(false);
                bouton.current?.focus();
              }}
              aria-label="Fermer"
            >
              ×
            </button>
          </div>
          {intro && <p className="sig-intro">{intro}</p>}
          {propres.length === 0 && <p className="sig-vide">{vide}</p>}
          {propres.map((l, i) => (
            <div className="sig" key={i}>
              <span className="lib">{l.texte}</span>
              <span className={`force ${l.force === "rassurant" ? "rassure" : l.force}`}>
                {l.points != null ? `+${l.points} pt${l.points > 1 ? "s" : ""}` : LIB_FORCE[l.force]}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
