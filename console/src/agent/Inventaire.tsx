// Inventaire des agents IA d'Orbis Pay (GET /api/agents, champ `inventaire`) :
// une carte par agent, avec son nom, son propriétaire, ses outils, ses droits en
// trop, son niveau de risque expliqué et sa résistance mesurée sur le banc.
// Les agents qui attendent une décision passent en tête.

import { useMemo } from "react";
import type { AgentInventaire, Incident, Session, Signal } from "../types";
import { Pourquoi, type Force, type LignePourquoi } from "../ui/Pourquoi";
import { attendDecision, decoder, estATraiter, libelleDroit, sansCodes } from "../ui/mots";
import { tempsRelatif } from "../ui/primitives";

const NIVEAU: Record<string, { lib: string; cls: string }> = {
  eleve: { lib: "Risque élevé", cls: "eleve" },
  moyen: { lib: "Risque moyen", cls: "moyen" },
  faible: { lib: "Risque faible", cls: "faible" },
};

function dateCourte(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

// Ce que les signaux du tri disent de l'agent. Un signal absent n'est pas une
// preuve : il n'apparaît pas. Ce qui ressemble à un humain rassure, en vert.
function lignesSignaux(signaux: Signal[]): LignePourquoi[] {
  const sortie: LignePourquoi[] = [];
  for (const s of signaux) {
    if (s.present === false) continue;
    const texte = sansCodes(decoder(s.libelle ?? ""));
    if (!texte) continue;
    let force: Force;
    if (s.categorie === "humain" || s.poids <= 0) force = "rassurant";
    else if (s.poids >= 0.35) force = "fort";
    else if (s.poids >= 0.15) force = "moyen";
    else force = "faible";
    sortie.push({ texte, force });
  }
  return sortie;
}

function forcePoints(points: number): Force {
  if (points >= 4) return "fort";
  if (points >= 2) return "moyen";
  return "faible";
}

interface Vue {
  agent: AgentInventaire;
  sessions: Session[];
  incidents: Incident[];
  attente: Incident | undefined;
  aTraiter: Incident | undefined;
  etat: { lib: string; cls: string };
}

function etatAgent(sessions: Session[], incidents: Incident[], attente?: Incident): { lib: string; cls: string } {
  if (attente) return { lib: "Attend votre décision", cls: "attente" };
  const derniere = [...sessions].sort((a, b) => (b.derniere_vue ?? "").localeCompare(a.derniere_vue ?? ""))[0];
  if (!derniere) return { lib: "Aucune activité", cls: "neutre" };
  if (derniere.etat === "coupee") return { lib: "Coupé par le SOC", cls: "neutre" };
  if (derniere.etat === "suspendue") return { lib: "Action refusée par Dédale", cls: "ok" };
  const inc = incidents.find((i) => i.session_id === derniere.id);
  if (inc?.statut === "surveille") return { lib: "Action laissée passer, surveillé", cls: "neutre" };
  return { lib: "En service", cls: "neutre" };
}

export function InventaireAgents({
  inventaire,
  sessions,
  incidents,
  ouvrirIncident,
  ecrireRegle,
}: {
  inventaire: AgentInventaire[];
  sessions: Session[];
  incidents: Incident[];
  ouvrirIncident: (id: string) => void;
  ecrireRegle: (agent: AgentInventaire) => void;
}) {
  const vues = useMemo<Vue[]>(() => {
    const liste = inventaire.map((agent) => {
      const s = sessions.filter((x) => x.source === "interne" && x.agent === agent.id);
      const ids = new Set(s.map((x) => x.id));
      const incs = incidents
        .filter((i) => ids.has(i.session_id))
        .sort((a, b) => (b.ouvert_le ?? "").localeCompare(a.ouvert_le ?? ""));
      const attente = incs.find(attendDecision);
      const aTraiter = incs.find(estATraiter);
      return { agent, sessions: s, incidents: incs, attente, aTraiter, etat: etatAgent(s, incs, attente) };
    });
    // Décision attendue d'abord, puis à traiter, puis le risque le plus haut.
    return liste.sort(
      (a, b) =>
        Number(Boolean(b.attente)) - Number(Boolean(a.attente)) ||
        Number(Boolean(b.aTraiter)) - Number(Boolean(a.aTraiter)) ||
        b.agent.risque.score - a.agent.risque.score
    );
  }, [inventaire, sessions, incidents]);

  if (vues.length === 0) return <div className="vide">Aucun agent déclaré pour l'instant.</div>;

  return (
    <div className="inv-grille">
      {vues.map((v) => (
        <CarteAgent key={v.agent.id} v={v} ouvrirIncident={ouvrirIncident} ecrireRegle={ecrireRegle} />
      ))}
    </div>
  );
}

function CarteAgent({
  v,
  ouvrirIncident,
  ecrireRegle,
}: {
  v: Vue;
  ouvrirIncident: (id: string) => void;
  ecrireRegle: (agent: AgentInventaire) => void;
}) {
  const a = v.agent;
  const niveau = NIVEAU[a.risque.niveau] ?? NIVEAU.faible;
  const sortants = a.outils.filter((o) => o.sortant).length;
  const res = a.resistance;
  const signaux = v.sessions.flatMap((s) => s.signaux ?? []);
  const lignes: LignePourquoi[] = [
    ...a.risque.raisons.map((r) => ({ texte: r.texte, force: forcePoints(r.points), points: r.points })),
    ...lignesSignaux(signaux),
  ];
  const incident = v.attente ?? v.aTraiter ?? v.incidents[0];

  return (
    <article className={`inv-carte ${v.attente ? "inv-attente" : ""}`} aria-labelledby={`inv-${a.id}`}>
      <header className="inv-tete">
        <div>
          <h3 id={`inv-${a.id}`} className="inv-nom">{a.nom}</h3>
          <p className="inv-proprio">
            {a.proprietaire ?? "Propriétaire non déclaré"}
            {a.declare === false && " · absent du registre"}
          </p>
        </div>
        <span className={`statut-pill s-${v.etat.cls}`}>
          <span className="pt" />
          {v.etat.lib}
        </span>
      </header>

      {a.role && <p className="inv-role">{a.role}</p>}

      <dl className="inv-faits">
        <div>
          <dt>Outils</dt>
          <dd>
            {a.outils.length} outil{a.outils.length > 1 ? "s" : ""}
            {sortants > 0 && <span className="inv-doux">, dont {sortants} qui font sortir des données ou de l'argent</span>}
          </dd>
        </div>
        <div>
          <dt>Droits en trop</dt>
          <dd>
            {a.droits.surplus.length === 0 ? (
              <span className="inv-doux">aucun</span>
            ) : (
              <span className="inv-puces">
                {a.droits.surplus.slice(0, 3).map((c) => (
                  <span key={c} className="inv-puce" title={c}>
                    {libelleDroit(c)}
                  </span>
                ))}
                {a.droits.surplus.length > 3 && (
                  <span
                    className="inv-puce inv-puce-plus"
                    title={a.droits.surplus.slice(3).map((c) => libelleDroit(c)).join(", ")}
                  >
                    +{a.droits.surplus.length - 3}
                  </span>
                )}
              </span>
            )}
          </dd>
        </div>
        <div>
          <dt>Résistance</dt>
          <dd>
            {res && res.mesure !== false && res.score != null && res.essais ? (
              <>
                {res.essais - (res.suivis ?? 0)} contenus piégés sur {res.essais} n'ont pas abouti
                <span className="inv-doux">
                  {" "}
                  · trafic synthétique{res.date ? ` · ${dateCourte(res.date)}` : ""}
                </span>
              </>
            ) : (
              <span className="inv-doux">jamais mesurée sur le banc</span>
            )}
          </dd>
        </div>
        <div>
          <dt>Activité</dt>
          <dd>
            {a.appels} action{a.appels > 1 ? "s" : ""} sur {a.sessions} session{a.sessions > 1 ? "s" : ""}
            {a.derniere_activite && <span className="inv-doux"> · {tempsRelatif(a.derniere_activite)}</span>}
          </dd>
        </div>
      </dl>

      <footer className="inv-pied">
        <span className={`inv-risque r-${niveau.cls}`}>
          {niveau.lib}
          <span className="inv-points">{a.risque.score} pts</span>
        </span>
        <Pourquoi
          titre={`Pourquoi ce niveau de risque`}
          intro="Chaque point vient d'un fait que Dédale a vu ou que l'inventaire déclare."
          lignes={lignes}
        />
        <span className="inv-espace" />
        <button type="button" className="lien-incident" onClick={() => ecrireRegle(a)}>
          Écrire une règle
        </button>
        {incident && (
          <button
            type="button"
            className={`lien-incident ${v.attente ? "lien-attente" : ""}`}
            onClick={() => ouvrirIncident(incident.id)}
          >
            {v.attente ? "Décider" : "Voir l'incident"}
          </button>
        )}
      </footer>
    </article>
  );
}
