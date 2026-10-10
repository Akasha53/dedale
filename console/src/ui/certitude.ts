// Certitude d'un incident : une seule source (la synthèse du backend), un seul
// texte. Le résumé « Ce qui s'est passé » et le pré-tri l'écrivent avec cette
// fonction, pour qu'un juré ne lise jamais deux chiffres sur le même dossier.
// Un appel retenu par une règle fixe de la passerelle n'a pas de pourcentage :
// on nomme la règle.

import type { Certitude } from "../types";

export type VueCertitude =
  | { genre: "regle"; texte: string; regle: string }
  | { genre: "score"; texte: string; pct: number; niveau: "haute" | "moyenne" | "basse" };

export function lireCertitude(c: Certitude | null | undefined): VueCertitude | null {
  if (!c) return null;
  if (c.regle) return { genre: "regle", texte: `Règle ${c.regle}`, regle: c.regle };
  if (typeof c.score !== "number") return null;
  const brut = c.score > 1 ? c.score / 100 : c.score;
  const pct = Math.round(Math.min(1, Math.max(0, brut)) * 100);
  const niveau = pct >= 75 ? "haute" : pct >= 50 ? "moyenne" : "basse";
  return { genre: "score", texte: `Sûr à ${pct} %`, pct, niveau };
}
