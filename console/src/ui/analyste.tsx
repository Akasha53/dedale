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

// Signature demandée : quand une décision ou une règle part sans nom, le
// sélecteur de l'en-tête s'ouvre et attend le nom au lieu de signer
// « analyste ».
let demande: { ok: (nom: string) => void; ko: (e: Error) => void } | null = null;
const ecouteursDemande = new Set<() => void>();

function signalerDemande() {
  ecouteursDemande.forEach((f) => f());
}

// Nom à signer : celui choisi, sinon on le demande dans l'en-tête.
export function exigerAnalyste(): Promise<string> {
  if (courant) return Promise.resolve(courant);
  demande?.ko(new Error("Une autre décision attend votre nom."));
  return new Promise((ok, ko) => {
    demande = { ok, ko };
    signalerDemande();
  });
}

function repondreDemande(nom: string | null) {
  const d = demande;
  demande = null;
  signalerDemande();
  if (!d) return;
  if (nom) d.ok(nom);
  else d.ko(new Error("Indiquez votre nom en haut à droite : il signe la décision dans le journal."));
}

// Un nom de remplacement (« analyste », vide) ne signe rien.
export function nomValide(nom?: string | null): boolean {
  const n = (nom ?? "").trim();
  return n.length >= 2 && !/^analyste(-soc)?$/i.test(n);
}

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
  const [attendu, setAttendu] = useState(false);
  const champ = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const suivre = () => {
      setAttendu(demande !== null);
      if (demande !== null) setEdition(true);
    };
    ecouteursDemande.add(suivre);
    return () => {
      ecouteursDemande.delete(suivre);
    };
  }, []);

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
    repondreDemande(nomValide(brouillon) ? brouillon.trim() : null);
  };

  if (edition)
    return (
      <form
        className={`analyste analyste-edition ${attendu ? "analyste-attendu" : ""}`}
        onSubmit={(e) => {
          e.preventDefault();
          valider();
        }}
      >
        <label htmlFor="analyste-nom">{attendu ? "Votre nom, pour signer" : "Analyste"}</label>
        <input
          id="analyste-nom"
          ref={champ}
          value={brouillon}
          maxLength={40}
          placeholder="Votre nom"
          autoComplete="off"
          onChange={(e) => setBrouillon(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              setEdition(false);
              repondreDemande(null);
            }
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
