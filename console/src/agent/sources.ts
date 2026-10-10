// Contenu lu par un agent, affiché en entier quand on clique sur l'étape
// « Lecture » de la boîte noire. Le backend l'envoie désarmé (liens en hxxps,
// domaines en [.], clés masquées) avec la partie piégée repérée : sur le
// maillon source de la chaîne, et sur GET /api/incidents/{id}/source. La
// console le rend comme du texte, jamais comme du HTML.

import type { DocumentSource, Incident, SourceLue } from "../types";
import { decoderEntites } from "./preuve";

const GENRES: Record<string, SourceLue["genre"]> = {
  mail: "mail",
  document: "document",
  outil: "outil",
  appel: "document",
  memoire: "document",
};

const NOTES: Record<string, string> = {
  mail: "La partie surlignée s'adresse à l'agent IA. Une personne qui lit ce mail ne la remarque pas.",
  document: "La partie surlignée est cachée dans le document : une personne qui l'ouvre ne la voit pas.",
  outil: "Seul un agent IA lit la description d'un outil. La partie surlignée est l'instruction cachée.",
};

function dateLisible(iso?: string): string | undefined {
  if (!iso) return undefined;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

// Découpe le corps en morceaux normaux et piégés : segments s'ils sont là,
// sinon positions `piege`, sinon `texte_piege` cherché dans le corps.
function morceauxDe(doc: DocumentSource): SourceLue["morceaux"] {
  if (doc.segments?.length) return doc.segments.map((s) => ({ texte: decoderEntites(s.texte), piege: Boolean(s.piege) }));
  const corps = doc.corps ?? "";
  const zones = [...(doc.piege ?? [])].filter((z) => z.fin > z.debut).sort((a, b) => a.debut - b.debut);
  if (zones.length) {
    const sortie: SourceLue["morceaux"] = [];
    let i = 0;
    for (const z of zones) {
      if (z.debut > i) sortie.push({ texte: decoderEntites(corps.slice(i, z.debut)) });
      sortie.push({ texte: decoderEntites(corps.slice(z.debut, z.fin)), piege: true });
      i = z.fin;
    }
    if (i < corps.length) sortie.push({ texte: decoderEntites(corps.slice(i)) });
    return sortie;
  }
  const piege = doc.texte_piege ?? "";
  const pos = piege ? corps.indexOf(piege) : -1;
  if (pos >= 0) {
    return [
      { texte: decoderEntites(corps.slice(0, pos)) },
      { texte: decoderEntites(piege), piege: true },
      { texte: decoderEntites(corps.slice(pos + piege.length)) },
    ].filter((m) => m.texte);
  }
  return [{ texte: decoderEntites(corps) }];
}

// Autour d'un bloc surligné, les sauts de ligne du texte voisin feraient un
// grand vide : on les retire.
function ajuster(morceaux: SourceLue["morceaux"]): SourceLue["morceaux"] {
  return morceaux
    .map((m, i) => {
      if (m.piege) return { ...m, texte: m.texte.trim() };
      let t = m.texte;
      if (morceaux[i - 1]?.piege) t = t.replace(/^\s+/, "");
      if (morceaux[i + 1]?.piege) t = t.replace(/\s+$/, "");
      return { ...m, texte: t };
    })
    .filter((m) => m.texte);
}

export function versSourceLue(doc: DocumentSource): SourceLue {
  const genre = GENRES[doc.type ?? ""] ?? "document";
  return {
    genre,
    titre: decoderEntites(doc.titre ?? "Contenu lu par l'agent"),
    de: doc.expediteur ? decoderEntites(doc.expediteur) : doc.origine === "externe" ? "extérieur à Orbis Pay" : undefined,
    a: doc.destinataire ? decoderEntites(doc.destinataire) : undefined,
    date: dateLisible(doc.date),
    morceaux: ajuster(morceauxDe(doc)),
    note: NOTES[genre],
  };
}

// Document porté par l'incident : champ dédié, maillon source de la chaîne,
// ou événement source du journal.
export function documentDe(inc: Incident): DocumentSource | null {
  const deChaine = (inc.chaine ?? []).find((m) => m.document_source)?.document_source;
  if (deChaine) return deChaine;
  for (const e of inc.evenements ?? []) {
    const d = (e.details ?? {}) as Record<string, unknown>;
    if (d.document_source && typeof d.document_source === "object") return d.document_source as DocumentSource;
  }
  return null;
}

// Ce que la console affiche dans le panneau, sans attendre le réseau.
export function sourcePour(inc: Incident): SourceLue {
  if (inc.source_lue) return inc.source_lue;
  const doc = documentDe(inc);
  if (doc) return versSourceLue(doc);
  const nom = (inc.evenements ?? [])
    .map((e) => ((e.details ?? {}) as Record<string, unknown>).source as Record<string, unknown> | undefined)
    .map((s) => s?.document)
    .find((d): d is string => typeof d === "string");
  const mcp = (inc.evenements ?? []).find((e) => ((e.details ?? {}) as Record<string, unknown>).outil_mcp_suspect);
  return {
    genre: mcp ? "outil" : "document",
    titre: nom ? `« ${nom} »` : mcp?.outil ? `Outil « ${mcp.outil} »` : "Contenu lu par l'agent",
    morceaux: [
      {
        texte:
          "Le texte complet n'a pas été transmis à la console. Dédale en garde une empreinte pour la preuve, sans recopier l'instruction cachée.",
      },
    ],
  };
}
