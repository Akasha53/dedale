// Règles du SOC écrites en français : l'analyste écrit une phrase, Dédale la
// reformule (« Voilà ce que j'ai compris… Activer ? ») et rien ne s'applique
// avant son accord. Les règles actives se retirent d'un clic confirmé.

import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { useDonnees } from "../api/store";
import type { AnalysePolitique, Politique } from "../types";
import { useAnalyste } from "../ui/analyste";
import { decoder, majuscule } from "../ui/mots";
import { heure } from "../ui/primitives";

export interface ReglesPoignee {
  preremplir: (debut: string) => void;
}

const EFFET: Record<string, string> = {
  bloquer: "bloque",
  retenir: "met en attente",
  alerter: "prévient",
};

const EXEMPLES = [
  "L'agent de tri des mails ne doit jamais envoyer de mail hors d'Orbis Pay",
  "Aucun agent ne fait de virement le week-end",
];

export const PanneauRegles = forwardRef<ReglesPoignee>(function PanneauRegles(_props, ref) {
  const { politiques, analyserPolitique, activerPolitique, retirerPolitique } = useDonnees();
  const analyste = useAnalyste();
  const [phrase, setPhrase] = useState("");
  const [analyse, setAnalyse] = useState<AnalysePolitique | null>(null);
  const [occupe, setOccupe] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const [fait, setFait] = useState<string | null>(null);
  const champ = useRef<HTMLTextAreaElement>(null);
  const zone = useRef<HTMLElement>(null);

  useImperativeHandle(ref, () => ({
    preremplir: (debut: string) => {
      setPhrase(debut);
      setAnalyse(null);
      setErreur(null);
      zone.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      window.setTimeout(() => {
        const c = champ.current;
        if (!c) return;
        c.focus({ preventScroll: true });
        c.setSelectionRange(debut.length, debut.length);
      }, 350);
    },
  }));

  useEffect(() => {
    if (!fait) return;
    const t = window.setTimeout(() => setFait(null), 6000);
    return () => window.clearTimeout(t);
  }, [fait]);

  const proposer = async () => {
    if (!phrase.trim() || occupe) return;
    setOccupe(true);
    setErreur(null);
    setFait(null);
    try {
      setAnalyse(await analyserPolitique(phrase.trim()));
    } catch (e) {
      setErreur(e instanceof Error ? e.message : "La phrase n'a pas pu être relue.");
    } finally {
      setOccupe(false);
    }
  };

  const activer = async () => {
    if (!analyse?.comprise || occupe) return;
    setOccupe(true);
    setErreur(null);
    try {
      const p = await activerPolitique(analyse.phrase, analyse.regle, analyste || "analyste");
      setFait(`Règle n°${p.numero} active.`);
      setPhrase("");
      setAnalyse(null);
    } catch (e) {
      setErreur(e instanceof Error ? e.message : "La règle n'a pas pu être activée.");
    } finally {
      setOccupe(false);
    }
  };

  return (
    <section className="panneau regles" aria-labelledby="regles-titre" ref={zone}>
      <div className="titre">
        <span id="regles-titre">Règles du SOC</span>
        <span className="droite">écrites en français, actives après votre accord</span>
      </div>
      <div className="corps">
        <form
          className="regle-saisie"
          onSubmit={(e) => {
            e.preventDefault();
            void proposer();
          }}
        >
          <label htmlFor="regle-phrase" className="regle-lib">
            Écrire une règle
          </label>
          <div className="regle-ligne">
            <textarea
              id="regle-phrase"
              ref={champ}
              rows={1}
              value={phrase}
              maxLength={500}
              placeholder={EXEMPLES[0]}
              onChange={(e) => {
                setPhrase(e.target.value);
                setAnalyse(null);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void proposer();
                }
              }}
            />
            <button type="submit" className="regle-btn" disabled={!phrase.trim() || occupe}>
              {occupe && !analyse ? "Lecture…" : "Proposer"}
            </button>
          </div>
        </form>

        {analyse && (
          <div className={`regle-reponse ${analyse.comprise ? "" : "incomprise"}`} role="status">
            <p>{decoder(analyse.texte)}</p>
            {analyse.comprise && (
              <div className="regle-choix">
                <button type="button" className="regle-btn primaire" onClick={() => void activer()} disabled={occupe}>
                  {occupe ? "Activation…" : "Activer"}
                </button>
                <button
                  type="button"
                  className="regle-btn"
                  onClick={() => {
                    setAnalyse(null);
                    champ.current?.focus();
                  }}
                >
                  Corriger la phrase
                </button>
              </div>
            )}
          </div>
        )}
        {fait && <p className="regle-fait" role="status">{fait}</p>}
        {erreur && <p className="decision-erreur" role="alert">{erreur}</p>}

        {politiques.length === 0 ? (
          <p className="regle-vide">Aucune règle active. Exemple : « {EXEMPLES[1]} ».</p>
        ) : (
          <ul className="regle-liste" aria-label="Règles actives">
            {politiques.map((p) => (
              <LigneRegle key={p.id} p={p} retirer={() => retirerPolitique(p.id, analyste || "analyste")} />
            ))}
          </ul>
        )}
      </div>
    </section>
  );
});

function LigneRegle({ p, retirer }: { p: Politique; retirer: () => Promise<void> }) {
  const [confirme, setConfirme] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  useEffect(() => {
    if (!confirme) return;
    const t = window.setTimeout(() => setConfirme(false), 5000);
    return () => window.clearTimeout(t);
  }, [confirme]);
  const enonce = majuscule(decoder(p.enonce || p.texte.replace(/^règle n°\d+ : /, "")));
  const effet = EFFET[p.effet ?? ""] ?? null;
  const n = p.declenchements ?? 0;
  return (
    <li className="regle-item">
      <span className="regle-num">n°{p.numero}</span>
      <span className="regle-texte">
        {enonce}
        <span className="regle-meta">
          {effet ? `Dédale ${effet} l'action. ` : ""}
          {n === 0 ? "Jamais déclenchée" : `Déclenchée ${n} fois${p.dernier_declenchement ? `, dernière à ${heure(p.dernier_declenchement).slice(0, 5)}` : ""}`}
          {p.par ? ` · activée par ${p.par}` : ""}
        </span>
        {erreur && <span className="decision-erreur">{erreur}</span>}
      </span>
      <button
        type="button"
        className={`regle-retirer ${confirme ? "confirme" : ""}`}
        onClick={() => {
          if (!confirme) {
            setConfirme(true);
            return;
          }
          setConfirme(false);
          retirer().catch((e) => setErreur(e instanceof Error ? e.message : "Retrait impossible."));
        }}
      >
        {confirme ? "Confirmer le retrait" : "Retirer"}
      </button>
    </li>
  );
}
