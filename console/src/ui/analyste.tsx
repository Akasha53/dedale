// L'analyste qui décide : son nom signe chaque décision au journal. Il est gardé
// dans ce navigateur seulement (localStorage), jamais envoyé ailleurs qu'avec une
// décision. Le sélecteur reste discret, en haut à droite.

import { useEffect, useRef, useState, useSyncExternalStore } from "react";

const CLE = "dedale.analyste";
const ecouteurs = new Set<() => void>();

function lire(): string {
  try {
    return window.localStorage.getItem(CLE) ?? "";
  } catch {
    return "";
  }
}

let courant = lire();

export function definirAnalyste(nom: string): void {
  courant = nom.trim().slice(0, 40);
  try {
    if (courant) window.localStorage.setItem(CLE, courant);
    else window.localStorage.removeItem(CLE);
  } catch {
    // Stockage indisponible (navigation privée) : le nom vaut pour cette page.
  }
  ecouteurs.forEach((f) => f());
}

export function useAnalyste(): string {
  return useSyncExternalStore(
    (f) => {
      ecouteurs.add(f);
      return () => ecouteurs.delete(f);
    },
    () => courant
  );
}

export function SelecteurAnalyste() {
  const nom = useAnalyste();
  const [edition, setEdition] = useState(false);
  const [brouillon, setBrouillon] = useState(nom);
  const champ = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (edition) {
      setBrouillon(nom);
      champ.current?.focus();
      champ.current?.select();
    }
  }, [edition, nom]);

  const valider = () => {
    definirAnalyste(brouillon);
    setEdition(false);
  };

  if (edition)
    return (
      <form
        className="analyste analyste-edition"
        onSubmit={(e) => {
          e.preventDefault();
          valider();
        }}
      >
        <label htmlFor="analyste-nom">Analyste</label>
        <input
          id="analyste-nom"
          ref={champ}
          value={brouillon}
          maxLength={40}
          placeholder="Votre nom"
          autoComplete="off"
          onChange={(e) => setBrouillon(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") setEdition(false);
          }}
          onBlur={valider}
        />
      </form>
    );

  return (
    <button
      type="button"
      className={`analyste ${nom ? "" : "analyste-vide"}`}
      onClick={() => setEdition(true)}
      title="Ce nom signe vos décisions dans le journal"
    >
      <span className="analyste-lib">Analyste :</span> {nom || "à indiquer"}
    </button>
  );
}
