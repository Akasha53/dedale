// Règles du SOC écrites en français : l'analyste écrit une phrase, Dédale la
// reformule (« Voilà ce que j'ai compris… Activer ? ») et rien ne s'applique
// avant son accord. Les règles actives se retirent d'un clic confirmé.
// « Retire les droits en trop aux agents » se lit à part : une ligne par agent
// avec les droits qui partiront, et « Rendre les droits » pour annuler.
// Chaque phrase lance une instance de l'agent des règles, qui prépare un
// changement (créer, modifier, retirer une règle, retirer des droits) puis se
// ferme. Le changement ne s'applique qu'au clic sur « Appliquer ».

import { forwardRef, useEffect, useImperativeHandle, useRef, useState, type CSSProperties } from "react";
import { useDonnees } from "../api/store";
import type { AnalysePolitique, Politique } from "../types";
import { useAnalyste } from "../ui/analyste";
import { decoder, libelleDroit, majuscule } from "../ui/mots";
import { heure } from "../ui/primitives";

const MOINDRE = "moindre_privilege";
const EXEMPLE_MOINDRE = "Retire les droits en trop aux agents";

// Champs que le backend ajoute pour le moindre privilège et le lecteur de la
// phrase (modèle ou motifs). Tous facultatifs : un backend plus ancien ne les
// envoie pas et le panneau retombe sur le texte seul.
interface DroitVu {
  code: string;
  libelle?: string;
}
interface LigneRetrait {
  agent: string;
  nom?: string;
  droits: (DroitVu | string)[];
  deja_retires?: string[];
}
interface Changement {
  type: "creation" | "modification" | "retrait" | "retrait_droits" | (string & {});
  id?: string;
  numero?: number;
  intention?: string;
  rien_a_retirer?: boolean;
}
interface EtapeAgent {
  outil: string;
  libelle: string;
  verdict: string;
}
interface SessionAgent {
  session: string;
  numero: number;
  appels: number;
  refus?: number;
  etat: string;
  modele?: string | null;
  etapes?: EtapeAgent[];
  jeton_revoque?: boolean;
  duree_ms?: number | null;
  raison_fin?: string | null;
}
type Analyse = AnalysePolitique & {
  intention?: string;
  compris_par?: string | null;
  repli?: string | null;
  lecteur?: { moteur?: string; modele?: string | null; duree_ms?: number | null };
  plan?: LigneRetrait[];
  entete?: string;
  conclusion?: string;
  changement?: Changement | null;
  agent_regles?: SessionAgent | null;
  refusee?: boolean;
};
type PolitiqueVue = Politique & { intention?: string; retraits?: LigneRetrait[] };

function codeDe(d: DroitVu | string): string {
  return typeof d === "string" ? d : d.code;
}

function nomDroit(d: DroitVu | string): string {
  return typeof d === "string" ? majuscule(libelleDroit(d)) : majuscule(libelleDroit(d.code, d.libelle));
}

function nomModele(m?: string | null): string {
  const bas = (m ?? "").toLowerCase();
  for (const n of ["haiku", "sonnet", "opus"]) if (bas.includes(n)) return n.charAt(0).toUpperCase() + n.slice(1);
  return "le modèle";
}

// « Compris par le modèle (Haiku, 2,4 s) » ou « Compris par les motifs ».
function lecture(a: Analyse): string | null {
  if (!a.compris_par) return null;
  if (a.compris_par === "modèle") {
    const ms = a.lecteur?.duree_ms;
    const duree = ms != null ? `, ${(ms / 1000).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} s` : "";
    return `Compris par le modèle (${nomModele(a.lecteur?.modele)}${duree})`;
  }
  // Repli : dit pourquoi le modèle n'a pas lu (« le modèle a mis trop de temps »).
  return a.repli ? `Lu par les motifs : ${a.repli.replace(/ : lecture par motifs$/, "")}.` : "Lu par les motifs.";
}

function secondes(ms?: number | null): string {
  return `${((ms ?? 0) / 1000).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} s`;
}

// « Agent des règles (Haiku) · session regles-0012 · lit les règles · prépare la
// modification · session fermée · jeton révoqué · 2 appels en 7,8 s », rempli au
// fil des appels.
function traceAgent(s: SessionAgent): string {
  const morceaux = [`Agent des règles (${nomModele(s.modele)}) · session ${s.session}`];
  for (const e of s.etapes ?? []) morceaux.push(e.verdict === "refuse" ? `${e.libelle}, refusé` : e.libelle);
  if (s.etat === "fermée") {
    const n = s.appels;
    morceaux.push(
      `session fermée${s.jeton_revoque === false ? "" : " · jeton révoqué"} · ${n} appel${n > 1 ? "s" : ""} en ${secondes(s.duree_ms)}`
    );
  }
  return morceaux.join(" · ");
}

// Suivi de l'instance pendant qu'elle travaille : `GET /api/politiques/agent`.
// Hors ligne (console sur le mock), la route n'existe pas et rien ne s'affiche.
async function derniereSession(): Promise<number | null> {
  try {
    const r = await fetch("/api/politiques/agent");
    if (!r.ok) return null;
    const d = (await r.json()) as { derniere?: number };
    return typeof d.derniere === "number" ? d.derniere : null;
  } catch {
    return null;
  }
}

async function suivreSession(apres: number, arret: { fini: boolean }, maj: (s: SessionAgent) => void) {
  while (!arret.fini) {
    try {
      const r = await fetch(`/api/politiques/agent?apres=${apres}`);
      if (r.ok) {
        const d = (await r.json()) as { session?: SessionAgent | null };
        if (d.session && !arret.fini) maj(d.session);
      }
    } catch {
      /* backend muet : on attend la réponse de l'analyse */
    }
    await new Promise((ok) => window.setTimeout(ok, 300));
  }
}

function nonCompris(a: Analyse): string | null {
  if (a.comprise || a.refusee || !a.repli) return null;
  return `Ni le modèle ni les motifs n'ont trouvé de règle : ${a.repli}.`;
}

function applicable(a: Analyse): boolean {
  if (!a.comprise) return false;
  return Boolean(a.regle) || (a.changement?.type === "retrait" && Boolean(a.changement.id));
}

function PucesDroits({ droits, neutre }: { droits: (DroitVu | string)[]; neutre?: boolean }) {
  return (
    <span className="inv-puces">
      {droits.map((d) => (
        <span
          key={codeDe(d)}
          className="inv-puce"
          title={codeDe(d)}
          style={neutre ? { background: "var(--survol)", color: "var(--texte-doux)" } : undefined}
        >
          {nomDroit(d)}
        </span>
      ))}
    </span>
  );
}

const STYLE_AGENTS: CSSProperties = { listStyle: "none", margin: "10px 0", padding: 0, display: "grid", gap: 8 };
const STYLE_AGENT: CSSProperties = { display: "grid", gap: 4 };
const STYLE_NOM: CSSProperties = { fontSize: 14, fontWeight: 500 };
const STYLE_EXEMPLE: CSSProperties = {
  border: 0,
  background: "transparent",
  padding: 0,
  font: "inherit",
  color: "var(--texte-doux)",
  textDecoration: "underline dotted",
  textUnderlineOffset: 3,
  cursor: "pointer",
};

function ReformulationMoindre({ a }: { a: Analyse }) {
  const plan = a.plan ?? [];
  return (
    <>
      <p>{decoder(a.entete ?? "Voilà ce que j'ai compris : retirer les droits en trop.")}</p>
      <ul style={STYLE_AGENTS} aria-label="Droits qui seront retirés">
        {plan.map((l) => (
          <li key={l.agent} style={STYLE_AGENT}>
            <span style={STYLE_NOM}>{l.nom ?? l.agent}</span>
            {l.droits.length > 0 ? (
              <PucesDroits droits={l.droits} />
            ) : (
              <span className="inv-doux" style={{ fontSize: 13.5 }}>
                aucun droit en trop
                {l.deja_retires && l.deja_retires.length > 0
                  ? `, ${l.deja_retires.length} déjà retiré${l.deja_retires.length > 1 ? "s" : ""}`
                  : ""}
              </span>
            )}
          </li>
        ))}
      </ul>
      {a.conclusion && <p>{decoder(a.conclusion)}</p>}
    </>
  );
}

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
  const [agent, setAgent] = useState<SessionAgent | null>(null);
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
    setAnalyse(null);
    setAgent(null);
    const arret = { fini: false };
    const apres = await derniereSession();
    if (apres !== null) void suivreSession(apres, arret, setAgent);
    try {
      const a = (await analyserPolitique(phrase.trim())) as Analyse;
      arret.fini = true;
      setAgent(a.agent_regles ?? null);
      setAnalyse(a);
    } catch (e) {
      setErreur(e instanceof Error ? e.message : "La phrase n'a pas pu être relue.");
    } finally {
      arret.fini = true;
      setOccupe(false);
    }
  };

  const activer = async () => {
    if (!analyse || !applicable(analyse as Analyse) || occupe) return;
    const ch = (analyse as Analyse).changement;
    setOccupe(true);
    setErreur(null);
    try {
      if (ch?.type === "retrait" && ch.id) {
        // Retirer une règle passe par la route existante, comme le bouton « Retirer ».
        await retirerPolitique(ch.id, analyste || "analyste");
        setFait(ch.intention === MOINDRE ? `Droits rendus : règle n°${ch.numero} retirée.` : `Règle n°${ch.numero} retirée.`);
        setPhrase("");
        setAnalyse(null);
        setAgent(null);
        return;
      }
      const p = (await activerPolitique(analyse.phrase, analyse.regle, analyste || "analyste")) as PolitiqueVue;
      if (ch?.type === "modification") {
        setFait(`Règle n°${ch.numero} remplacée par la règle n°${p.numero}.`);
      } else if (p.intention === MOINDRE && p.retraits) {
        const n = p.retraits.reduce((t, l) => t + l.droits.length, 0);
        const agents = p.retraits.length;
        setFait(
          `Règle n°${p.numero} active : ${n} droit${n > 1 ? "s" : ""} retiré${n > 1 ? "s" : ""} à ${agents} agent${agents > 1 ? "s" : ""}.`
        );
      } else {
        setFait(`Règle n°${p.numero} active.`);
      }
      setPhrase("");
      setAnalyse(null);
      setAgent(null);
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
                setAgent(null);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void proposer();
                }
              }}
            />
            <button type="submit" className="regle-btn" disabled={!phrase.trim() || occupe}>
              {occupe && !analyse ? "L'agent lit…" : "Proposer"}
            </button>
          </div>
        </form>
        {(agent || (analyse && (analyse as Analyse).lecteur?.moteur === "motifs")) && (
          <p className="regle-vide" style={{ marginTop: 8 }} aria-live="polite">
            {agent ? traceAgent(agent) : "Lu par les motifs de sAIfe, sans modèle."}
          </p>
        )}
        <p className="regle-vide" style={{ marginTop: 8 }}>
          Exemple :{" "}
          <button
            type="button"
            style={STYLE_EXEMPLE}
            onClick={() => {
              setPhrase(EXEMPLE_MOINDRE);
              setAnalyse(null);
              champ.current?.focus();
            }}
          >
            « {EXEMPLE_MOINDRE} »
          </button>
        </p>

        {analyse && (
          <div className={`regle-reponse ${analyse.comprise ? "" : "incomprise"}`} role="status">
            {(analyse as Analyse).intention === MOINDRE && (analyse as Analyse).plan ? (
              <ReformulationMoindre a={analyse as Analyse} />
            ) : (
              <p>{decoder(analyse.texte)}</p>
            )}
            {(lecture(analyse as Analyse) ?? nonCompris(analyse as Analyse)) && (
              <span className="regle-meta" style={{ marginTop: 8 }}>
                {lecture(analyse as Analyse) ?? nonCompris(analyse as Analyse)}
              </span>
            )}
            {applicable(analyse as Analyse) && (
              <div className="regle-choix">
                <button type="button" className="regle-btn primaire" onClick={() => void activer()} disabled={occupe}>
                  {(analyse as Analyse).changement
                    ? occupe
                      ? "Application…"
                      : "Appliquer"
                    : occupe
                      ? "Activation…"
                      : "Activer"}
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

function LigneRegle({ p, retirer }: { p: PolitiqueVue; retirer: () => Promise<void> }) {
  const [confirme, setConfirme] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  useEffect(() => {
    if (!confirme) return;
    const t = window.setTimeout(() => setConfirme(false), 5000);
    return () => window.clearTimeout(t);
  }, [confirme]);
  const moindre = p.intention === MOINDRE && Array.isArray(p.retraits);
  const enonce = majuscule(decoder(p.enonce || p.texte.replace(/^règle n°\d+ : /, "")));
  const effet = EFFET[p.effet ?? ""] ?? null;
  const n = p.declenchements ?? 0;
  const derniere = p.dernier_declenchement ? `, dernier à ${heure(p.dernier_declenchement).slice(0, 5)}` : "";
  return (
    <li className="regle-item">
      <span className="regle-num">n°{p.numero}</span>
      <span className="regle-texte">
        {moindre ? (
          <>
            Droits en trop retirés
            <ul style={{ ...STYLE_AGENTS, margin: "6px 0 2px", gap: 6 }}>
              {p.retraits!.map((l) => (
                <li key={l.agent} style={STYLE_AGENT}>
                  <span style={{ fontSize: 13.5 }}>{l.nom ?? l.agent}</span>
                  <PucesDroits droits={l.droits} neutre />
                </li>
              ))}
            </ul>
          </>
        ) : (
          enonce
        )}
        <span className="regle-meta">
          {moindre
            ? `La passerelle refuse les outils qui les exigent. ${n === 0 ? "Aucun appel refusé" : `${n} appel${n > 1 ? "s" : ""} refusé${n > 1 ? "s" : ""}${derniere}`}`
            : `${effet ? `sAIfe ${effet} l'action. ` : ""}${n === 0 ? "Jamais déclenchée" : `Déclenchée ${n} fois${p.dernier_declenchement ? `, dernière à ${heure(p.dernier_declenchement).slice(0, 5)}` : ""}`}`}
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
          retirer().catch((e) =>
            setErreur(e instanceof Error ? e.message : moindre ? "Les droits n'ont pas pu être rendus." : "Retrait impossible.")
          );
        }}
      >
        {moindre ? (confirme ? "Confirmer : rendre les droits" : "Rendre les droits") : confirme ? "Confirmer le retrait" : "Retirer"}
      </button>
    </li>
  );
}
