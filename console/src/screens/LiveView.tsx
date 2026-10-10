import { useEffect, useMemo, useRef, useState } from "react";
import { useDonnees } from "../api/store";
import type { Activite, GestesHumains, Incident, Pilier, Session, Signal } from "../types";
import {
  appartientPilier,
  JaugeScore,
  PILIERS,
  SegmentsPiliers,
  Spinner,
  heure,
  tempsRelatif,
} from "../ui/primitives";
import { TexteCanary } from "../ui/Canary";
import { desarmer } from "../agent/preuve";
import { attendDecision, decoder, estATraiter, libelleOutil, nomAgent, raisonActivite, refusDOffice, sansCodes, VERDICT } from "../ui/mots";

const FIL_COURT = 8;

export function LiveView({
  ouvrirIncident,
  pilier,
  setPilier,
}: {
  ouvrirIncident: (id: string) => void;
  pilier: Pilier;
  setPilier: (p: Pilier) => void;
}) {
  const { sessions, incidents, mesures, activite, chargement } = useDonnees();

  const dansVue = sessions.filter((s) => appartientPilier(s.source, pilier));
  const incidentsVue = incidents.filter((i) => appartientPilier(i.source, pilier));

  const comptes = useMemo(() => {
    const c = { humain: 0, interne: 0 } as Record<Pilier, number>;
    for (const p of PILIERS) c[p.id] = sessions.filter((s) => appartientPilier(s.source, p.id)).length;
    return c;
  }, [sessions]);

  // Dernier incident de chaque session : celui qu'ouvre le lien de la ligne.
  const incidentParSession = useMemo(() => {
    const m = new Map<string, Incident>();
    for (const i of [...incidents].sort((a, b) => (a.ouvert_le ?? "").localeCompare(b.ouvert_le ?? "")))
      m.set(i.session_id, i);
    return m;
  }, [incidents]);

  // Les plus suspects d'abord.
  const triees = [...dansVue].sort((a, b) => b.score - a.score);
  const compteurs =
    pilier === "interne"
      ? compteursAgents(dansVue, incidentsVue, activite)
      : compteursSalaries(dansVue, mesures?.gestes_humains);

  return (
    <>
      <SegmentsPiliers pilier={pilier} setPilier={setPilier} comptes={comptes} />

      <div className="grille-compteurs">
        {compteurs.map((c) => (
          <div key={c.lib} className={`compteur ${c.alerte ? "alerte" : ""}`}>
            <div className="lib">{c.lib}</div>
            <div className="val">{c.val}</div>
            <div className="sous">{c.sous}</div>
          </div>
        ))}
      </div>

      {pilier === "interne" && (
        <FilAgents activite={activite} incidents={incidents} chargement={chargement} ouvrirIncident={ouvrirIncident} />
      )}

      <div className="panneau">
        <div className="titre">
          {pilier === "interne" ? "Les agents" : "Les postes"}
          <span className="droite">les plus suspects en haut</span>
        </div>
        {chargement ? (
          <Spinner texte="Connexion…" />
        ) : triees.length === 0 ? (
          <div className="vide">
            {pilier === "interne" ? "Aucun agent IA surveillé pour l'instant." : "Aucun poste surveillé pour l'instant."}
          </div>
        ) : (
          <div className="liste-sessions">
            {triees.map((s) => (
              <LigneSession key={s.id} s={s} incident={incidentParSession.get(s.id)} ouvrirIncident={ouvrirIncident} />
            ))}
          </div>
        )}
      </div>
    </>
  );
}

type Compteur = { lib: string; val: number; sous: string; alerte?: boolean };

function compteursAgents(agents: Session[], incidents: Incident[], activite: Activite[]): Compteur[] {
  const aDecider = incidents.filter(attendDecision).length;
  const arretees = activite.filter((a) => a.verdict !== "autorise").length;
  return [
    { lib: "Agents surveillés", val: agents.length, sous: "agents IA d'Orbis Pay" },
    { lib: "À décider", val: aDecider, sous: "actions retenues par Dédale", alerte: aDecider > 0 },
    {
      lib: "Actions arrêtées",
      val: arretees,
      sous: activite.length ? `sur les ${activite.length} dernières actions` : "aucune action récente",
    },
  ];
}

function compteursSalaries(postes: Session[], gestes: GestesHumains | undefined): Compteur[] {
  const passes = gestes?.passes_outre ?? 0;
  return [
    { lib: "Postes protégés", val: postes.length, sous: "salariés avec Dédale" },
    { lib: "Arrêtés à temps", val: gestes?.arretes ?? 0, sous: "le salarié a annulé après l'alerte" },
    { lib: "Continués malgré l'alerte", val: passes, sous: "remontés au SOC", alerte: passes > 0 },
  ];
}

// ---------- fil des agents ----------

function FilAgents({
  activite,
  incidents,
  chargement,
  ouvrirIncident,
}: {
  activite: Activite[];
  incidents: Incident[];
  chargement: boolean;
  ouvrirIncident: (id: string) => void;
}) {
  const [tout, setTout] = useState(false);
  // Une action retenue n'attend plus rien une fois son incident tranché.
  const enAttente = useMemo(
    () => new Set(incidents.filter(attendDecision).map((i) => i.id)),
    [incidents]
  );
  const lignes = tout ? activite : activite.slice(0, FIL_COURT);
  return (
    <section className="panneau fil" aria-labelledby="fil-titre">
      <div className="titre">
        <span id="fil-titre">Ce que font les agents en ce moment</span>
        <span className="fil-legende" aria-hidden="true">
          <span className="fil-pt ok" /> autorisée
          <span className="fil-pt attente" /> retenue
          <span className="fil-pt refus" /> refusée
        </span>
      </div>
      {chargement ? (
        <Spinner texte="Connexion…" />
      ) : activite.length === 0 ? (
        <div className="vide">Aucune action d'agent pour l'instant.</div>
      ) : (
        <>
          <ol className="fil-liste" aria-live="polite">
            {lignes.map((a) => (
              <LigneActivite
                key={a.id}
                a={a}
                enAttente={!a.incident_id || enAttente.has(a.incident_id)}
                ouvrirIncident={ouvrirIncident}
              />
            ))}
          </ol>
          {activite.length > FIL_COURT && (
            <button type="button" className="fil-plus" onClick={() => setTout((v) => !v)}>
              {tout ? "Afficher moins" : `Afficher les ${activite.length} dernières actions`}
            </button>
          )}
        </>
      )}
    </section>
  );
}

function LigneActivite({
  a,
  enAttente,
  ouvrirIncident,
}: {
  a: Activite;
  enAttente: boolean;
  ouvrirIncident: (id: string) => void;
}) {
  const v = VERDICT[a.verdict] ?? VERDICT.autorise;
  return (
    <li className={`fil-ligne v-${v.cls}`}>
      <time className="fil-heure" dateTime={a.heure}>{heure(a.heure)}</time>
      <span className={`fil-verdict v-${v.cls}`}>
        <span className="fil-pt" />
        {v.lib}
      </span>
      <span className="fil-texte" title={a.raison ? desarmer(decoder(a.raison)) : undefined}>
        <strong>{nomAgent(a.agent)}</strong> veut {libelleOutil(a.outil)}
        <span className="fil-raison">
          {" · "}
          <TexteCanary texte={raisonActivite(a, enAttente)} />
        </span>
      </span>
      {a.incident_id && a.verdict !== "autorise" ? (
        <button type="button" className="lien-incident" onClick={() => ouvrirIncident(a.incident_id!)}>
          Voir l'incident
        </button>
      ) : (
        <span />
      )}
    </li>
  );
}

// ---------- agents et postes ----------

function statutSession(s: Session, inc?: Incident): { lib: string; cls: string } {
  const ouvert = inc && estATraiter(inc);
  if (s.source === "humain") {
    return ouvert ? { lib: "Geste risqué signalé", cls: "attente" } : { lib: "Rien à signaler", cls: "ok" };
  }
  if (s.etat === "coupee") return { lib: "Arrêté", cls: "neutre" };
  if (s.etat === "suspendue" && inc && refusDOffice(inc)) return { lib: "Action refusée par Dédale", cls: "ok" };
  if (s.etat === "suspendue") return { lib: "En pause, attend votre décision", cls: "attente" };
  if (s.classement === "agent_ia" && ouvert) return { lib: "Détourné, surveillé", cls: "alerte" };
  return { lib: "Normal", cls: "ok" };
}

function nomSession(s: Session): string {
  if (s.source === "humain") return s.user_agent || s.id;
  return nomAgent(s.agent ?? undefined);
}

function LigneSession({
  s,
  incident,
  ouvrirIncident,
}: {
  s: Session;
  incident?: Incident;
  ouvrirIncident: (id: string) => void;
}) {
  const statut = statutSession(s, incident);
  return (
    <div className="session-ligne">
      <div className="idc">
        <span className="nom">{nomSession(s)}</span>
        <span className="srcv">
          {s.droits?.tache ? `${s.droits.tache.replace(/_/g, " ")} · ` : ""}vu {tempsRelatif(s.derniere_vue)}
        </span>
      </div>

      <div>
        <span className={`statut-pill s-${statut.cls}`}>
          <span className="pt" />
          {statut.lib}
        </span>
      </div>

      <div className="score-cell" title="Niveau de suspicion, de 0 à 100">
        <span className="score-lib">suspicion</span>
        <JaugeScore score={s.score} />
      </div>

      <div className="session-actions">
        {incident && (
          <button type="button" className="lien-incident" onClick={() => ouvrirIncident(incident.id)}>
            Voir l'incident
          </button>
        )}
        <Signaux s={s} />
      </div>
    </div>
  );
}

// « Pourquoi ? » : survol pour un aperçu, clic pour garder l'explication
// ouverte. Échap, la croix ou un clic ailleurs la referment.
function Signaux({ s }: { s: Session }) {
  const [epingle, setEpingle] = useState(false);
  const [survol, setSurvol] = useState(false);
  const zone = useRef<HTMLDivElement>(null);
  const ouvert = epingle || survol;

  useEffect(() => {
    if (!epingle) return;
    const dehors = (e: MouseEvent) => {
      if (zone.current && !zone.current.contains(e.target as Node)) setEpingle(false);
    };
    const echap = (e: KeyboardEvent) => {
      if (e.key === "Escape") setEpingle(false);
    };
    document.addEventListener("mousedown", dehors);
    document.addEventListener("keydown", echap);
    return () => {
      document.removeEventListener("mousedown", dehors);
      document.removeEventListener("keydown", echap);
    };
  }, [epingle]);

  const n = s.signaux?.length ?? 0;
  return (
    <div className="sig-wrap" ref={zone} onMouseEnter={() => setSurvol(true)} onMouseLeave={() => setSurvol(false)}>
      <button
        type="button"
        className={`sig-btn ${epingle ? "epingle" : ""}`}
        onClick={() => setEpingle((v) => !v)}
        aria-expanded={ouvert}
      >
        Pourquoi ? <span className="sig-n">{n}</span>
      </button>
      {ouvert && (
        <div className="sig-pop" role="dialog" aria-label="Pourquoi Dédale le signale">
          <div className="sig-tete">
            <h4>Pourquoi Dédale le signale</h4>
            {epingle ? (
              <button type="button" className="sig-fermer" onClick={() => setEpingle(false)} aria-label="Fermer">
                ×
              </button>
            ) : (
              <span className="sig-astuce">cliquez pour garder ouvert</span>
            )}
          </div>
          {n === 0 && <p className="sig-vide">Rien de particulier pour l'instant.</p>}
          {(s.signaux ?? []).map((sig, i) => (
            <LigneSignal key={i} sig={sig} />
          ))}
        </div>
      )}
    </div>
  );
}

function forceSignal(poids: number): { lib: string; cls: string } {
  if (poids <= 0) return { lib: "rassurant", cls: "rassure" };
  if (poids >= 0.35) return { lib: "signe fort", cls: "fort" };
  if (poids >= 0.15) return { lib: "signe moyen", cls: "moyen" };
  return { lib: "signe faible", cls: "faible" };
}

function LigneSignal({ sig }: { sig: Signal }) {
  const f = forceSignal(sig.poids);
  return (
    <div className="sig">
      <span className="lib">{sansCodes(decoder(sig.libelle))}</span>
      <span className={`force ${f.cls}`}>{f.lib}</span>
    </div>
  );
}
