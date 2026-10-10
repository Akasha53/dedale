// Garde-fous d'une décision lourde : confirmation avec un motif court, puis cinq
// secondes pour annuler avant que la décision parte. Le nom de l'analyste signe
// la décision ; s'il manque, on le demande ici.

import { useCallback, useEffect, useRef, useState } from "react";
import { definirAnalyste, useAnalyste } from "./analyste";

export const DELAI_ANNULATION_MS = 5000;

// Téléphone : le gros bouton tombe sous le pouce, on confirme toujours.
export function estPetitEcran(): boolean {
  try {
    return window.matchMedia("(max-width: 760px)").matches;
  } catch {
    return false;
  }
}

export function BlocConfirmation({
  titre,
  aide,
  libelle,
  danger,
  motifObligatoire,
  confirmer,
  annuler,
}: {
  titre: string;
  aide?: string;
  libelle: string;
  danger?: boolean;
  motifObligatoire: boolean;
  confirmer: (motif: string) => void;
  annuler: () => void;
}) {
  const analyste = useAnalyste();
  const [motif, setMotif] = useState("");
  const [nom, setNom] = useState(analyste);
  const champ = useRef<HTMLInputElement>(null);
  const nomRequis = !analyste;
  const motifOk = !motifObligatoire || motif.trim().length >= 3;
  const nomOk = !nomRequis || nom.trim().length >= 2;

  useEffect(() => {
    champ.current?.focus();
  }, []);

  const valider = () => {
    if (!motifOk || !nomOk) return;
    if (nomRequis) definirAnalyste(nom);
    confirmer(motif.trim());
  };

  return (
    <form
      className={`confirmation ${danger ? "danger" : ""}`}
      onSubmit={(e) => {
        e.preventDefault();
        valider();
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.stopPropagation();
          annuler();
        }
      }}
    >
      <p className="confirmation-titre">{titre}</p>
      {aide && <p className="confirmation-aide">{aide}</p>}
      {nomRequis && (
        <label className="confirmation-champ">
          <span>Votre nom, il signe la décision</span>
          <input
            ref={champ}
            value={nom}
            maxLength={40}
            autoComplete="off"
            onChange={(e) => setNom(e.target.value)}
          />
        </label>
      )}
      <label className="confirmation-champ">
        <span>{motifObligatoire ? "Motif (obligatoire)" : "Motif (facultatif)"}</span>
        <input
          ref={nomRequis ? undefined : champ}
          value={motif}
          maxLength={200}
          autoComplete="off"
          placeholder={motifObligatoire ? "En quelques mots, pourquoi" : ""}
          onChange={(e) => setMotif(e.target.value)}
        />
      </label>
      <div className="confirmation-boutons">
        <button type="submit" className={`confirmation-ok ${danger ? "danger" : ""}`} disabled={!motifOk || !nomOk}>
          {libelle}
        </button>
        <button type="button" className="confirmation-annuler" onClick={annuler}>
          Annuler
        </button>
      </div>
    </form>
  );
}

export interface Differee<A> {
  action: A;
  motif: string;
  fin: number;
}

// Une décision confirmée attend cinq secondes avant de partir. Changer de dossier
// l'annule : rien ne part sur un écran qu'on ne regarde plus.
export function useDifferee<A>(envoyer: (action: A, motif: string) => void, cle: string) {
  const [attente, setAttente] = useState<Differee<A> | null>(null);
  const [maintenant, setMaintenant] = useState(() => Date.now());
  const envoyerRef = useRef(envoyer);
  envoyerRef.current = envoyer;

  useEffect(() => setAttente(null), [cle]);

  useEffect(() => {
    if (!attente) return;
    const tic = window.setInterval(() => setMaintenant(Date.now()), 200);
    const depart = window.setTimeout(() => {
      setAttente(null);
      envoyerRef.current(attente.action, attente.motif);
    }, Math.max(0, attente.fin - Date.now()));
    return () => {
      window.clearInterval(tic);
      window.clearTimeout(depart);
    };
  }, [attente]);

  const lancer = useCallback((action: A, motif: string) => {
    setMaintenant(Date.now());
    setAttente({ action, motif, fin: Date.now() + DELAI_ANNULATION_MS });
  }, []);
  const annuler = useCallback(() => setAttente(null), []);
  const restant = attente ? Math.max(0, Math.ceil((attente.fin - maintenant) / 1000)) : 0;
  return { attente, restant, lancer, annuler };
}

export function BandeauAnnulation({ texte, restant, annuler }: { texte: string; restant: number; annuler: () => void }) {
  const bouton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    bouton.current?.focus();
  }, []);
  return (
    <div className="annulation" role="status" aria-live="assertive">
      <span className="annulation-compte" aria-hidden="true">
        {restant}
      </span>
      <span className="annulation-texte">
        {texte} dans {restant} s.
      </span>
      <button type="button" ref={bouton} className="annulation-btn" onClick={annuler}>
        Annuler
      </button>
    </div>
  );
}
