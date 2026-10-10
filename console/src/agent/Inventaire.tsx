// Inventaire des agents IA d'Orbis Pay (GET /api/agents, champ `inventaire`) :
// une carte par agent, avec son nom, son propriétaire, ses outils, ses droits en
// trop, son niveau de risque expliqué et sa résistance mesurée sur le banc.
// Les agents qui attendent une décision passent en tête.

import { useEffect, useMemo, useState } from "react";
import { useDonnees } from "../api/store";
import type { AgentInventaire, Incident, Politique, Session, Signal } from "../types";
import { useAnalyste } from "../ui/analyste";
import { Pourquoi, type Force, type LignePourquoi } from "../ui/Pourquoi";
import { attendDecision, decoder, estATraiter, libelleDroit, sansCodes } from "../ui/mots";
import { heure, tempsRelatif } from "../ui/primitives";
import { estAgentDedale } from "../ui/compteurs";

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

// « 1 point », « 2 points ».
function points(n: number): string {
  return `${n} point${n > 1 ? "s" : ""}`;
}

// Libellé lisible d'un outil : « Convertir un montant (outil externe) ».
function libelleOutil(o: { nom: string; libelle?: string }): string {
  return (o.libelle ?? o.nom).replace(/\(MCP externe\)/i, "(outil externe)");
}

// Une raison du risque, en clair. Les outils qui font sortir des données sont nommés,
// pour que l'analyste puisse vérifier le compte du backend.
function texteRaison(a: AgentInventaire, raison: AgentInventaire["risque"]["raisons"][number]): string {
  if (raison.code !== "outils_sortants" || !raison.references?.length) return raison.texte;
  const noms = raison.references.map((ref) => {
    const o = a.outils.find((x) => x.nom === ref);
    return o ? libelleOutil(o) : ref;
  });
  return `${raison.texte.replace(/\.$/, "")} : ${noms.join(", ")}.`;
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

  // Les agents d'Orbis Pay en cartes ; ceux de Dédale (l'agent des règles) dans une rangée
  // compacte à part : aucune règle du SOC ne peut les viser, ils n'ont pas de droits en trop.
  const orbis = vues.filter((v) => !estAgentDedale(v.agent.id, v.agent));
  const dedale = vues.filter((v) => estAgentDedale(v.agent.id, v.agent));

  return (
    <>
      {orbis.length > 0 && (
        <div className="inv-grille">
          {orbis.map((v) => (
            <CarteAgent key={v.agent.id} v={v} ouvrirIncident={ouvrirIncident} ecrireRegle={ecrireRegle} />
          ))}
        </div>
      )}
      {dedale.length > 0 && (
        <section className="inv-dedale" aria-labelledby="inv-dedale-titre">
          <h4 id="inv-dedale-titre" className="inv-dedale-titre">
            {dedale.length > 1 ? "Les agents de sAIfe" : "L'agent de sAIfe"}
          </h4>
          {dedale.map((v) => (
            <LigneAgentDedale key={v.agent.id} v={v} ouvrirIncident={ouvrirIncident} />
          ))}
        </section>
      )}
    </>
  );
}

// Rangée compacte d'un agent de Dédale : nom, ce qu'il fait, ses outils, son état et son
// risque, sur deux lignes. Pas de « Écrire une règle » : les règles du SOC ne le visent pas.
function LigneAgentDedale({ v, ouvrirIncident }: { v: Vue; ouvrirIncident: (id: string) => void }) {
  const a = v.agent;
  const niveau = NIVEAU[a.risque.niveau] ?? NIVEAU.faible;
  const lignes: LignePourquoi[] = a.risque.raisons.map((r) => ({
    texte: texteRaison(a, r),
    force: forcePoints(r.points),
    points: r.points,
  }));
  const incident = v.attente ?? v.aTraiter ?? v.incidents[0];
  const surplus = a.droits.surplus.length;
  const faits = [
    `${a.outils.length} outil${a.outils.length > 1 ? "s" : ""}`,
    surplus === 0 ? "aucun droit en trop" : `${surplus} droit${surplus > 1 ? "s" : ""} en trop`,
    a.appels > 0 ? `${a.appels} action${a.appels > 1 ? "s" : ""}` : null,
  ].filter(Boolean);
  return (
    <article className={`inv-ligne ${v.attente ? "inv-attente" : ""}`} aria-labelledby={`inv-${a.id}`}>
      <div className="inv-ligne-texte">
        <h3 id={`inv-${a.id}`} className="inv-nom" title={a.nom}>
          {a.nom}
        </h3>
        <p className="inv-ligne-meta">
          {[a.proprietaire ?? "Propriétaire non déclaré", ...faits].join(" · ")}
        </p>
        {a.role && (
          <p className="inv-role inv-role-court" title={a.role}>
            {a.role}
          </p>
        )}
      </div>
      <div className="inv-ligne-droite">
        <EtatAgent etat={v.etat} />
        <span className={`inv-risque r-${niveau.cls}`}>
          {niveau.lib}
          <span className="inv-points">{points(a.risque.score)}</span>
        </span>
        <Pourquoi
          titre="Pourquoi ce niveau de risque"
          intro="Chaque point vient d'un fait que sAIfe a vu ou que l'inventaire déclare."
          lignes={lignes}
        />
        {incident && (
          <button
            type="button"
            className={`lien-incident ${v.attente ? "lien-attente" : ""}`}
            onClick={() => ouvrirIncident(incident.id)}
          >
            {v.attente ? "Décider" : "Voir l'incident"}
          </button>
        )}
      </div>
    </article>
  );
}

// État d'un agent : un point et un mot. Le point porte la couleur quand elle a un sens
// (orange : une décision attend ; vert : Dédale a refusé l'action), le mot reste sobre.
function EtatAgent({ etat }: { etat: { lib: string; cls: string } }) {
  return (
    <span className={`inv-etat e-${etat.cls}`}>
      <span className="inv-etat-pt" aria-hidden="true" />
      {etat.lib}
    </span>
  );
}

// Droits en trop : les trois premiers, puis une puce « +N » qui déplie la liste complète.
// Un second clic la replie. C'est un vrai bouton : Entrée et Espace marchent au clavier.
const DROITS_VISIBLES = 3;

function PucesDroitsEnTrop({ codes, idListe }: { codes: string[]; idListe: string }) {
  const [deplie, setDeplie] = useState(false);
  const caches = codes.length - DROITS_VISIBLES;
  const visibles = deplie || caches <= 0 ? codes : codes.slice(0, DROITS_VISIBLES);
  return (
    <span className="inv-puces" id={idListe}>
      {visibles.map((c) => (
        <span key={c} className="inv-puce" title={libelleDroit(c)}>
          {libelleDroit(c)}
        </span>
      ))}
      {caches > 0 && (
        <button
          type="button"
          className="inv-puce inv-puce-plus"
          aria-expanded={deplie}
          aria-controls={idListe}
          aria-label={deplie ? "Replier la liste des droits en trop" : `Voir les ${caches} autres droits en trop`}
          onClick={() => setDeplie((d) => !d)}
        >
          {deplie ? "Replier" : `+${caches}`}
        </button>
      )}
    </span>
  );
}

// Droits retirés : chaque code, barré, puis la règle du SOC qui l'a retiré (qui, à
// quelle heure) et « Rendre les droits ». Un retrait fait depuis un incident n'a pas
// de règle : il s'affiche seul. Les détails viennent de `GET /api/politiques`, champ
// `retraits` des règles de moindre privilège (CONTRATS.md, avenant des règles).
type RegleRetrait = Politique & {
  intention?: string;
  retraits?: { agent: string; droits: (string | { code: string })[] }[];
};

const codeDroit = (d: string | { code: string }) => (typeof d === "string" ? d : d.code);

function DroitsRetires({ agent, codes }: { agent: string; codes: string[] }) {
  const { politiques, retirerPolitique } = useDonnees();
  const analyste = useAnalyste();
  const regles = useMemo(
    () =>
      (politiques as RegleRetrait[]).filter(
        (p) =>
          p.active !== false &&
          p.intention === "moindre_privilege" &&
          p.retraits?.some((l) => l.agent === agent && l.droits.some((d) => codes.includes(codeDroit(d))))
      ),
    [politiques, agent, codes]
  );
  return (
    <>
      <span className="inv-puces">
        {codes.map((c) => (
          <span key={c} className="inv-puce inv-puce-retire" title={`${c} : retiré`}>
            {libelleDroit(c)}
          </span>
        ))}
      </span>
      {regles.map((p) => (
        <RegleDuRetrait key={p.id} p={p} rendre={() => retirerPolitique(p.id, analyste || "analyste")} />
      ))}
    </>
  );
}

function RegleDuRetrait({ p, rendre }: { p: RegleRetrait; rendre: () => Promise<void> }) {
  const [confirme, setConfirme] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  useEffect(() => {
    if (!confirme) return;
    const t = window.setTimeout(() => setConfirme(false), 5000);
    return () => window.clearTimeout(t);
  }, [confirme]);
  const agents = p.retraits?.length ?? 1;
  const qui = [p.par ? `par ${p.par}` : null, p.creee_a ? `à ${heure(p.creee_a).slice(0, 5)}` : null]
    .filter(Boolean)
    .join(" ");
  return (
    <span className="inv-retrait">
      <span className="inv-doux">
        Retirés par la règle n°{p.numero}
        {qui ? `, ${qui}` : ""}
      </span>
      <button
        type="button"
        className={`lien-incident inv-rendre ${confirme ? "confirme" : ""}`}
        onClick={() => {
          if (!confirme) {
            setConfirme(true);
            return;
          }
          setConfirme(false);
          rendre().catch((e) => setErreur(e instanceof Error ? e.message : "Les droits n'ont pas pu être rendus."));
        }}
      >
        {confirme
          ? agents > 1
            ? `Confirmer : rendre les droits des ${agents} agents`
            : "Confirmer : rendre les droits"
          : "Rendre les droits"}
      </button>
      {erreur && <span className="decision-erreur">{erreur}</span>}
    </span>
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
  // Un outil dont le droit a été retiré est coupé : la passerelle le refuse. Les comptes
  // portent sur les outils encore actifs, comme `risque.raisons` du backend.
  const retires = new Set((a.droits.retires ?? []).map(codeDroit));
  const coupes = a.outils.filter((o) => o.droit && retires.has(o.droit)).length;
  const actifs = a.outils.length - coupes;
  const sortants = a.outils.filter((o) => o.sortant && !(o.droit && retires.has(o.droit))).length;
  const res = a.resistance;
  const signaux = v.sessions.flatMap((s) => s.signaux ?? []);
  const lignes: LignePourquoi[] = [
    ...a.risque.raisons.map((r) => ({ texte: texteRaison(a, r), force: forcePoints(r.points), points: r.points })),
    ...lignesSignaux(signaux),
  ];
  const incident = v.attente ?? v.aTraiter ?? v.incidents[0];

  return (
    <article className={`inv-carte ${v.attente ? "inv-attente" : ""}`} aria-labelledby={`inv-${a.id}`}>
      {/* Le titre prend toute la largeur : deux lignes au plus, puis une ellipse ; le nom
          complet reste au survol. L'état passe en dessous, avec le propriétaire. */}
      <header className="inv-tete">
        <h3 id={`inv-${a.id}`} className="inv-nom" title={a.nom}>
          {a.nom}
        </h3>
        <p className="inv-proprio">
          {a.proprietaire ?? "Propriétaire non déclaré"}
          {a.declare === false && " · absent du registre"}
        </p>
        <EtatAgent etat={v.etat} />
      </header>

      <p className="inv-role">{a.role ?? ""}</p>

      <dl className="inv-faits">
        <div>
          <dt>Outils</dt>
          <dd>
            {a.outils.length} outil{a.outils.length > 1 ? "s" : ""}
            {coupes > 0 ? (
              <span className="inv-doux">
                , dont {coupes} coupé{coupes > 1 ? "s" : ""}.{" "}
                {sortants > 0
                  ? `${sortants} des ${actifs} actifs ${sortants > 1 ? "peuvent" : "peut"} faire sortir des données ou de l'argent.`
                  : `Aucun des ${actifs} actifs ne fait sortir de données ni d'argent.`}
              </span>
            ) : (
              sortants > 0 && (
                <span className="inv-doux">
                  , dont {sortants} qui {sortants > 1 ? "font" : "fait"} sortir des données ou de l'argent
                </span>
              )
            )}
          </dd>
        </div>
        <div className="inv-fait-liste">
          <dt>Droits en trop</dt>
          <dd>
            {a.droits.surplus.length === 0 ? (
              <span className="inv-doux">aucun</span>
            ) : (
              <PucesDroitsEnTrop codes={a.droits.surplus} idListe={`inv-droits-${a.id}`} />
            )}
          </dd>
        </div>
        {(a.droits.retires ?? []).length > 0 && (
          <div className="inv-fait-liste">
            <dt>Droits retirés</dt>
            <dd>
              <DroitsRetires agent={a.id} codes={(a.droits.retires ?? []).map(codeDroit)} />
            </dd>
          </div>
        )}
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
          <span className="inv-points">{points(a.risque.score)}</span>
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
