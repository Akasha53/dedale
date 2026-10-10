// Panneau « Voir le mail » : le contenu lu par l'agent, en entier, avec la
// partie piégée surlignée. Texte désarmé, rendu comme du texte : aucun lien
// n'est cliquable. Si l'incident ne porte pas encore le document, on le
// demande au backend (GET /api/incidents/{id}/source).

import { useEffect, useRef, useState } from "react";
import { useDonnees } from "../api/store";
import type { Incident, Leurre, SourceLue } from "../types";
import { Icone } from "./icones";
import { desarmer } from "./preuve";
import { documentDe, sourcePour, versSourceLue } from "./sources";

// Sans texte transmis, on montre ce que Dédale sait du piège touché : jamais une
// fenêtre vide.
function depuisLeurre(incident: Incident, leurres: Leurre[], base: SourceLue): SourceLue {
  const ids = new Set(
    [
      ...(incident.chaine ?? []).map((m) => m.canari_id ?? m.leurre_id),
      ...(incident.evenements ?? []).map((e) => e.leurre_id),
    ].filter(Boolean) as string[]
  );
  const natures = ["consigne_cachee", "outil_mcp_piege", "canari_appel", "injection_chatbot", "memoire_empoisonnee", "canari_mail", "canari_document"];
  const l = leurres.find((x) => ids.has(x.id) && natures.includes(x.nature));
  if (!l) return base;
  return {
    ...base,
    titre: desarmer(l.emplacement) || base.titre,
    morceaux: [{ texte: desarmer(l.description), piege: true }],
    note: "La passerelle n'a pas transmis le texte d'origine. Voici ce que sAIfe sait du piège que l'agent a suivi.",
  };
}

const SOURCIL: Record<SourceLue["genre"], string> = {
  mail: "Le mail lu par l'agent",
  document: "Le document lu par l'agent",
  outil: "L'outil lu par l'agent",
};

export function ModaleSource({ incident, fermer }: { incident: Incident; fermer: () => void }) {
  const { getSource, leurres } = useDonnees();
  const [source, setSource] = useState<SourceLue>(() =>
    documentDe(incident) || incident.source_lue ? sourcePour(incident) : depuisLeurre(incident, leurres, sourcePour(incident))
  );
  const boite = useRef<HTMLDivElement>(null);
  const bouton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (documentDe(incident) || incident.source_lue) return;
    let vivant = true;
    getSource(incident.id)
      .then((docs) => {
        const doc = docs.find((d) => d.instruction_cachee || d.segments?.some((s) => s.piege)) ?? docs[0];
        if (vivant && doc) setSource(versSourceLue(doc));
      })
      .catch(() => undefined);
    return () => {
      vivant = false;
    };
  }, [incident, getSource]);

  useEffect(() => {
    const precedent = document.activeElement as HTMLElement | null;
    bouton.current?.focus();
    const touche = (e: KeyboardEvent) => {
      if (e.key === "Escape") fermer();
      // Le focus reste dans le panneau.
      if (e.key === "Tab" && boite.current) {
        const focusables = boite.current.querySelectorAll<HTMLElement>("button, [tabindex='0']");
        const premier = focusables[0];
        const dernier = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === premier) {
          e.preventDefault();
          dernier?.focus();
        } else if (!e.shiftKey && document.activeElement === dernier) {
          e.preventDefault();
          premier?.focus();
        }
      }
    };
    document.addEventListener("keydown", touche);
    const ancien = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", touche);
      document.body.style.overflow = ancien;
      precedent?.focus?.();
    };
  }, [fermer]);

  const piegee = source.morceaux.some((m) => m.piege);

  return (
    <div className="modale-fond" onMouseDown={fermer}>
      <div
        className="modale"
        role="dialog"
        aria-modal="true"
        aria-labelledby="modale-titre"
        ref={boite}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <header className="modale-tete">
          <div>
            <span className="ag-sourcil">{SOURCIL[source.genre]}</span>
            <h3 id="modale-titre">{source.titre}</h3>
          </div>
          <button type="button" className="modale-fermer" onClick={fermer} ref={bouton} aria-label="Fermer">
            <Icone nom="fermer" taille={16} />
          </button>
        </header>

        {(source.de || source.a || source.date) && (
          <dl className="modale-meta">
            {source.de && (
              <div>
                <dt>De</dt>
                <dd>{source.de}</dd>
              </div>
            )}
            {source.a && (
              <div>
                <dt>À</dt>
                <dd>{source.a}</dd>
              </div>
            )}
            {source.date && (
              <div>
                <dt>Reçu</dt>
                <dd>{source.date}</dd>
              </div>
            )}
          </dl>
        )}

        <div className="modale-corps" tabIndex={0}>
          {source.morceaux.map((m, i) =>
            m.piege ? (
              <mark key={i} className="piege">
                <span className="piege-lib">Instruction cachée</span>
                {m.texte}
              </mark>
            ) : (
              <span key={i}>{m.texte}</span>
            )
          )}
        </div>

        {piegee && source.note && <p className="modale-note">{source.note}</p>}
        <p className="modale-securite">
          Liens et adresses désarmés : rien ici n'est cliquable. Les noms et adresses des salariés sont masqués en partie.
        </p>
      </div>
    </div>
  );
}
