// Écran « agent IA » d'un incident interne : boîte noire en six maillons,
// décision Couper / Reprendre, accès accordés vs nécessaires et chrono.
// Tout texte de preuve passe par preuve.ts avant d'être affiché.

import { useEffect, useMemo, useRef, useState } from "react";
import { useDonnees } from "../api/store";
import type { DecisionAction, Droit, DroitsAgent, Incident } from "../types";
import { BadgeTypeIncident, codeDroit } from "../ui/primitives";
import { lireBoiteNoire, type Issue, type LectureAgent, type MaillonAgent } from "./boiteNoire";
import { Icone } from "./icones";
import { BadgesRefs } from "./references";

// ---------- temps ----------

function useMaintenant(actif: boolean): number {
  const [t, setT] = useState(() => Date.now());
  useEffect(() => {
    if (!actif) return;
    const id = setInterval(() => setT(Date.now()), 1000);
    return () => clearInterval(id);
  }, [actif]);
  return t;
}

function ms(iso?: string | null): number {
  if (!iso) return Number.NaN;
  return new Date(iso).getTime();
}

// Durée lisible : millisecondes sous la seconde, puis secondes, minutes, heures.
export function duree(delta: number): string {
  if (!Number.isFinite(delta)) return "—";
  if (delta < 1) return "< 1 ms";
  if (delta < 1000) return `${Math.round(delta)} ms`;
  const s = delta / 1000;
  if (s < 60) return `${s.toFixed(s < 10 ? 1 : 0).replace(".", ",")} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ${String(Math.floor(s % 60)).padStart(2, "0")} s`;
  return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")} min`;
}

// Heure à la milliseconde : les maillons d'un agent tombent souvent dans la
// même seconde, l'ordre doit rester lisible.
function heureFine(iso?: string): { hms: string; mil: string } | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return {
    hms: d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
    mil: `,${String(d.getMilliseconds()).padStart(3, "0")}`,
  };
}

function Heure({ iso, lib }: { iso?: string; lib?: string }) {
  const h = heureFine(iso);
  if (!h) return <span className="ag-heure ag-heure-vide">{lib ?? "non daté"}</span>;
  return (
    <time className="ag-heure" dateTime={iso}>
      {lib && <span className="ag-heure-lib">{lib} </span>}
      {h.hms}
      <span className="ag-heure-ms">{h.mil}</span>
    </time>
  );
}

// ---------- libellés d'état ----------

const ETAT_ISSUE: Record<Issue, { lib: string; chapo: (outil: string) => string }> = {
  attente: {
    lib: "Appel retenu",
    chapo: (o) => `La passerelle retient ${o}. Rien n'est sorti. Coupez la session ou reprenez l'appel.`,
  },
  coupee: {
    lib: "Coupée",
    chapo: (o) => `Session coupée et jeton révoqué : ${o} n'a pas été exécuté.`,
  },
  reprise: {
    lib: "Reprise",
    chapo: (o) => `Le SOC a libéré ${o}, tel quel. La session reste sous surveillance.`,
  },
  bloquee: {
    lib: "Bloquée",
    chapo: (o) => `${o} a été refusé hors droits et le jeton révoqué. Le dossier attend votre revue.`,
  },
  surveillee: {
    lib: "Active",
    chapo: () => "Session active, sans appel retenu.",
  },
};

function PiluleEtat({ issue }: { issue: Issue }) {
  return (
    <span className={`ag-etat ag-etat-${issue}`} key={issue}>
      <span className="ag-etat-point" />
      {ETAT_ISSUE[issue].lib}
    </span>
  );
}

// ---------- composant principal ----------

export function IncidentAgent({
  incident,
  majEnCours,
  decisionEnCours,
  erreurDecision,
  trancher,
}: {
  incident: Incident;
  majEnCours: boolean;
  decisionEnCours: DecisionAction | null;
  erreurDecision: string | null;
  trancher: (a: DecisionAction) => void;
}) {
  const { leurres, sessions } = useDonnees();
  const lecture = useMemo(() => lireBoiteNoire(incident, leurres), [incident, leurres]);
  const vivant = !lecture.derniereDecision && (lecture.issue === "attente" || lecture.issue === "bloquee");
  const maintenant = useMaintenant(vivant);
  const droits = incident.droits ?? sessions.find((s) => s.id === incident.session_id)?.droits ?? null;

  return (
    <div className="ag-dossier">
      <EnteteDossier incident={incident} lecture={lecture} maintenant={maintenant} majEnCours={majEnCours} />
      <div className="ag-grille">
        <Chaine lecture={lecture} maintenant={maintenant} />
        <PanneauDecision
          incident={incident}
          lecture={lecture}
          maintenant={maintenant}
          decisionEnCours={decisionEnCours}
          erreurDecision={erreurDecision}
          trancher={trancher}
        />
        <PanneauDroits droits={droits} lecture={lecture} />
      </div>
    </div>
  );
}

// ---------- en-tête et chrono ----------

function EnteteDossier({
  incident,
  lecture,
  maintenant,
  majEnCours,
}: {
  incident: Incident;
  lecture: LectureAgent;
  maintenant: number;
  majEnCours: boolean;
}) {
  const outil = lecture.appel?.outil ?? "l'appel";
  return (
    <section className="ag-coque ag-entete" aria-labelledby="ag-titre">
      <div className="ag-noyau">
        <div className="ag-entete-haut">
          <span className="ag-sourcil">Agent IA · {incident.id}</span>
          <BadgeTypeIncident type={incident.type} />
          <span className={`gravite ${incident.gravite}`}>{incident.gravite}</span>
          <PiluleEtat issue={lecture.issue} />
        </div>
        <h2 id="ag-titre" className="ag-titre">{incident.titre}</h2>
        <p className="ag-chapo">{ETAT_ISSUE[lecture.issue].chapo(outil)}</p>
        <Chrono incident={incident} lecture={lecture} maintenant={maintenant} />
        <div className="ag-entete-pied">
          <span className="ag-meta">
            session <span className="ag-mono">{incident.session_id}</span>
            {majEnCours ? " · mise à jour…" : ""}
          </span>
          <BadgesRefs refs={lecture.refs} legende />
        </div>
      </div>
    </section>
  );
}

function Chrono({ incident, lecture, maintenant }: { incident: Incident; lecture: LectureAgent; maintenant: number }) {
  const premiere =
    incident.temps_session?.premiere_vue ??
    [...(incident.evenements ?? [])].map((e) => e.horodatage).filter(Boolean).sort()[0] ??
    [...(incident.chaine ?? [])].map((m) => m.horodatage).filter(Boolean).sort()[0];
  const tDebut = ms(premiere);
  const tDetect = ms(lecture.detection ?? incident.temps_session?.detecte_a);
  const tRemonte = ms(incident.ouvert_le);
  const premiereDecision = incident.decisions?.[0];
  const tDecision = ms(premiereDecision?.horodatage);
  const enAttente = !premiereDecision;
  const ferme = incident.statut === "clos" || incident.statut === "ignore";

  const etapes = [
    {
      lib: "Détection",
      val: duree(tDetect - tDebut),
      sous: "après la première action",
    },
    {
      lib: "Remontée au SOC",
      val: duree(tRemonte - tDetect),
      sous: "incident ouvert",
    },
    {
      lib: "Décision humaine",
      val: enAttente ? (ferme ? "—" : duree(maintenant - tRemonte)) : duree(tDecision - tRemonte),
      sous: enAttente ? (ferme ? "aucune journalisée" : "en attente, le compteur tourne") : `par ${premiereDecision.analyste}`,
      vivant: enAttente && !ferme,
    },
  ];
  return (
    <div className="ag-chrono" role="group" aria-label="Chrono de détection et de remontée">
      <span className="ag-chrono-pic">
        <Icone nom="chrono" taille={16} />
      </span>
      {etapes.map((e) => (
        <div key={e.lib} className={`ag-chrono-etape ${e.vivant ? "vivant" : ""}`}>
          <span className="ag-chrono-lib">{e.lib}</span>
          <span className="ag-chrono-val">{e.val}</span>
          <span className="ag-chrono-sous">{e.sous}</span>
        </div>
      ))}
    </div>
  );
}

// ---------- boîte noire ----------

function Chaine({ lecture, maintenant }: { lecture: LectureAgent; maintenant: number }) {
  return (
    <section className="ag-coque ag-zone-chaine" aria-labelledby="ag-chaine-titre">
      <div className="ag-noyau">
        <header className="ag-carte-tete">
          <div>
            <span className="ag-sourcil">Boîte noire</span>
            <h3 id="ag-chaine-titre">Ce que l'agent a lu et tenté</h3>
          </div>
          <span className="ag-carte-note">
            {lecture.depuisJournal ? "lue dans le journal de session" : "lue dans la chaîne du backend"}
          </span>
        </header>
        <ol className="ag-fil" aria-hidden="true">
          {lecture.maillons.map((m) => (
            <li key={m.cle} className={`ton-${m.ton}`}>
              <span className="ag-fil-point" />
              <span className="ag-fil-lib">{m.lib}</span>
            </li>
          ))}
        </ol>
        <ol className="ag-maillons">
          {lecture.maillons.map((m, i) => (
            <Maillon key={m.cle} m={m} i={i} maintenant={maintenant} />
          ))}
        </ol>
      </div>
    </section>
  );
}

function Maillon({ m, i, maintenant }: { m: MaillonAgent; i: number; maintenant: number }) {
  return (
    <li className={`ag-maillon ton-${m.ton}`} style={{ ["--i" as string]: i }}>
      <div className="ag-rail">
        <span className="ag-noeud">
          <Icone nom={m.cle} taille={17} />
        </span>
      </div>
      <div className="ag-maillon-corps">
        <div className="ag-maillon-tete">
          <span className="ag-num">{String(i + 1).padStart(2, "0")}</span>
          <span className="ag-lib">{m.lib}</span>
          {m.nature && <span className="ag-nature">{m.nature}</span>}
          {(m.horodatage || m.ton !== "absent") && <Heure iso={m.horodatage} lib={m.horoLib} />}
        </div>
        <div className={`ag-maillon-titre ${m.cle === "appel" && m.ton !== "absent" ? "ag-mono" : ""}`}>{m.titre}</div>
        {m.enCours && m.horodatage && (
          <div className="ag-attente">
            <span className="ag-etat-point" /> en attente depuis {duree(maintenant - ms(m.horodatage))}
          </div>
        )}
        {m.texte && <p className="ag-maillon-texte">{m.texte}</p>}
        {m.preuve && (
          <figure className="ag-preuve">
            <figcaption>
              <Icone nom="bouclier" taille={13} />
              {m.preuveLib ?? "Preuve neutralisée"}
            </figcaption>
            <code>{m.preuve}</code>
          </figure>
        )}
        {(m.ids.length > 0 || m.refs.length > 0) && (
          <div className="ag-maillon-pied">
            {m.ids.map((id) => (
              <span key={id} className="ag-canari">canari {id}</span>
            ))}
            <BadgesRefs refs={m.refs} />
          </div>
        )}
      </div>
    </li>
  );
}

// ---------- décision ----------

const LIB_ACTION: Record<string, string> = {
  couper: "a coupé la session",
  valider_riposte: "a validé la riposte",
  reprendre: "a repris l'appel",
  ignorer: "a ignoré l'alerte",
  clore: "a clos le dossier",
};

function PanneauDecision({
  incident,
  lecture,
  maintenant,
  decisionEnCours,
  erreurDecision,
  trancher,
}: {
  incident: Incident;
  lecture: LectureAgent;
  maintenant: number;
  decisionEnCours: DecisionAction | null;
  erreurDecision: string | null;
  trancher: (a: DecisionAction) => void;
}) {
  const [confirme, setConfirme] = useState(false);
  const minuteur = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (minuteur.current) clearTimeout(minuteur.current);
  }, []);
  useEffect(() => setConfirme(false), [incident.id, lecture.issue]);

  const ferme = incident.statut === "clos" || incident.statut === "ignore";
  const occupe = decisionEnCours !== null;
  const peutCouper = !occupe && lecture.issue !== "coupee" && !ferme;
  const peutReprendre = !occupe && lecture.appelLiberable;

  const raisonReprise = lecture.appelLiberable
    ? confirme
      ? "L'appel part tel quel, avec ses paramètres. Seul cet appel est libéré."
      : "Libère seulement l'appel retenu. La session reste sous surveillance."
    : lecture.issue === "bloquee"
      ? "Rien à libérer : une action hors droits reste bloquée."
      : lecture.issue === "coupee"
        ? "Session coupée : plus rien à libérer."
        : lecture.issue === "reprise"
          ? "Appel déjà libéré."
          : ferme
            ? "Dossier fermé."
            : "Aucun appel retenu.";

  const cliquerReprendre = () => {
    if (!peutReprendre) return;
    if (!confirme) {
      setConfirme(true);
      if (minuteur.current) clearTimeout(minuteur.current);
      minuteur.current = setTimeout(() => setConfirme(false), 6000);
      return;
    }
    setConfirme(false);
    trancher("reprendre");
  };

  const etatLong: Record<Issue, string> = {
    attente: `Appel retenu depuis ${duree(maintenant - ms(lecture.detection))}`,
    coupee: "Session coupée, jeton révoqué",
    reprise: "Appel libéré, session surveillée",
    bloquee: "Action refusée, jeton déjà révoqué",
    surveillee: "Session active",
  };

  return (
    <section className={`ag-coque ag-zone-decision issue-${lecture.issue}`} aria-labelledby="ag-decision-titre">
      <div className="ag-noyau">
        <header className="ag-carte-tete">
          <div>
            <span className="ag-sourcil">Décision du SOC</span>
            <h3 id="ag-decision-titre" className="ag-etat-long" key={lecture.issue} aria-live="polite">
              <span className="ag-etat-point" />
              {etatLong[lecture.issue]}
            </h3>
          </div>
        </header>

        {lecture.appel && (
          <div className="ag-appel">
            <span className="ag-appel-lib">
              {lecture.issue === "attente" ? "Appel en suspens" : lecture.issue === "reprise" ? "Appel libéré" : "Appel visé"}
            </span>
            <code>{lecture.appel.preuve}</code>
          </div>
        )}

        <div className="ag-actions" aria-busy={occupe}>
          <div className="ag-action">
            <button
              type="button"
              className="ag-pilule ag-pilule-couper"
              disabled={!peutCouper}
              onClick={() => trancher("couper")}
            >
              <span>{decisionEnCours === "couper" ? "Coupure…" : "Couper"}</span>
              <span className="ag-rond">
                <Icone nom="couper" taille={15} />
              </span>
            </button>
            <p className="ag-aide">
              {lecture.issue === "coupee"
                ? "Déjà coupée."
                : lecture.issue === "reprise"
                  ? "Coupe la session pour la suite. L'appel libéré est déjà parti."
                  : "Suspend la session et révoque le jeton. Rien ne sort."}
            </p>
          </div>
          <div className="ag-action">
            <button
              type="button"
              className={`ag-pilule ag-pilule-reprendre ${confirme ? "confirme" : ""}`}
              disabled={!peutReprendre}
              onClick={cliquerReprendre}
            >
              <span>{decisionEnCours === "reprendre" ? "Reprise…" : confirme ? "Confirmer la reprise" : "Reprendre"}</span>
              <span className="ag-rond">
                <Icone nom="reprendre" taille={14} />
              </span>
            </button>
            <p className="ag-aide">
              {raisonReprise}
              {confirme && (
                <>
                  {" "}
                  <button type="button" className="ag-lien" onClick={() => setConfirme(false)}>
                    Annuler
                  </button>
                </>
              )}
            </p>
          </div>
        </div>

        {erreurDecision && (
          <p className="decision-erreur" role="alert">
            {erreurDecision}
          </p>
        )}

        {incident.decisions?.length > 0 && (
          <ol className="ag-journal" aria-label="Journal des décisions">
            {incident.decisions.map((d, i) => (
              <li key={i}>
                <Heure iso={d.horodatage} />
                <span>
                  {d.analyste} {LIB_ACTION[d.action] ?? d.action}
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}

// ---------- droits ----------

function PanneauDroits({ droits, lecture }: { droits: DroitsAgent | null; lecture: LectureAgent }) {
  if (!droits) {
    return (
      <section className="ag-coque ag-zone-droits" aria-labelledby="ag-droits-titre">
        <div className="ag-noyau">
          <header className="ag-carte-tete">
            <div>
              <span className="ag-sourcil">Moindre privilège</span>
              <h3 id="ag-droits-titre">Accès accordés vs nécessaires</h3>
            </div>
          </header>
          <p className="ag-note">
            Pas de jeton de tâche déclaré pour cette session : les droits accordés ne sont pas connus.
          </p>
          {lecture.scopesUtilises.length > 0 && (
            <>
              <div className="ag-droits-groupe-lib">Droits vus en action</div>
              <div className="ag-droits-puces">
                {lecture.scopesUtilises.map((s) => (
                  <span key={s} className="ag-droit">{s}</span>
                ))}
              </div>
            </>
          )}
        </div>
      </section>
    );
  }

  const libelles = new Map<string, string>();
  const noter = (d: Droit) => {
    if (typeof d !== "string" && d.libelle) libelles.set(d.code, d.libelle);
    return codeDroit(d);
  };
  const accordes = (droits.accordes ?? []).map(noter);
  const necessaires = new Set((droits.necessaires ?? []).map(noter));
  const utilises = new Set([...(droits.utilises ?? []).map(noter), ...lecture.scopesUtilises]);
  const tentatives = (droits.tentatives_hors_scope ?? []).filter((t) => t.scope_requis);
  const enTrop = accordes.filter((c) => !necessaires.has(c));
  const utiles = accordes.filter((c) => necessaires.has(c));
  const pct = accordes.length ? Math.round((enTrop.length / accordes.length) * 100) : 0;
  const titre = (c: string) => libelles.get(c) ?? c;

  return (
    <section className="ag-coque ag-zone-droits" aria-labelledby="ag-droits-titre">
      <div className="ag-noyau">
        <header className="ag-carte-tete">
          <div>
            <span className="ag-sourcil">Moindre privilège</span>
            <h3 id="ag-droits-titre">Accès accordés vs nécessaires</h3>
          </div>
        </header>
        <div className="ag-droits-chiffres">
          <div>
            <span className="ag-gros">{accordes.length}</span>
            <span className="ag-petit">accordés</span>
          </div>
          <div>
            <span className="ag-gros ag-cyan">{necessaires.size}</span>
            <span className="ag-petit">nécessaires</span>
          </div>
          <div>
            <span className="ag-gros ag-ambre">{enTrop.length}</span>
            <span className="ag-petit">en trop · {pct}{"\u00a0"}%</span>
          </div>
        </div>
        <div className="ag-barre-droits" role="img" aria-label={`${enTrop.length} droits accordés sur ${accordes.length} dépassent la tâche`}>
          {[...utiles, ...enTrop].map((c) => (
            <span
              key={c}
              className={`${necessaires.has(c) ? "nec" : "trop"} ${utilises.has(c) ? "util" : ""}`}
              title={`${titre(c)} (${c})`}
            />
          ))}
        </div>
        {droits.tache && (
          <p className="ag-note">
            Tâche <span className="ag-mono">{droits.tache}</span> : {necessaires.size} droit{necessaires.size > 1 ? "s" : ""} suffisent.
          </p>
        )}

        {tentatives.length > 0 && (
          <>
            <div className="ag-droits-groupe-lib">Demandé hors du jeton</div>
            <div className="ag-droits-puces">
              {tentatives.map((t, i) => (
                <span key={i} className="ag-droit refuse" title={titre(t.scope_requis!)}>
                  {t.scope_requis} <em>refusé</em>
                </span>
              ))}
            </div>
          </>
        )}
        <div className="ag-droits-groupe-lib">Nécessaires à la tâche</div>
        <div className="ag-droits-puces">
          {utiles.length === 0 && <span className="ag-note">aucun</span>}
          {utiles.map((c) => (
            <span key={c} className="ag-droit nec" title={titre(c)}>
              {c}
              {utilises.has(c) && <em>utilisé</em>}
            </span>
          ))}
        </div>
        <div className="ag-droits-groupe-lib">Accordés en trop</div>
        <div className="ag-droits-puces">
          {enTrop.length === 0 && <span className="ag-note">aucun</span>}
          {enTrop.map((c) => (
            <span key={c} className={`ag-droit trop ${utilises.has(c) ? "util" : ""}`} title={titre(c)}>
              {c}
              {utilises.has(c) && <em>utilisé</em>}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
