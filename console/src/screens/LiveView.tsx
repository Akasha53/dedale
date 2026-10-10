import { useMemo, useRef, useState } from "react";
import { useDonnees } from "../api/store";
import type { Activite, AgentInventaire, Incident, Pilier } from "../types";
import { SegmentsPiliers, Spinner, heure } from "../ui/primitives";
import { desarmer } from "../agent/preuve";
import { InventaireAgents } from "../agent/Inventaire";
import { AgentsPostes } from "../agent/AgentsPostes";
import { PanneauRegles, type ReglesPoignee } from "../agent/Regles";
import { ListePostes } from "../salarie/Postes";
import { compter } from "../ui/compteurs";
import { attendDecision, decoder, libelleOutil, majuscule, nomAgentPour, raisonActivite, VERDICT } from "../ui/mots";

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
  const { sessions, incidents, mesures, activite, inventaire, chargement } = useDonnees();
  const comptes = useMemo(() => compter(incidents, sessions, inventaire, activite), [incidents, sessions, inventaire, activite]);
  const regles = useRef<ReglesPoignee>(null);

  const compteurs: Compteur[] =
    pilier === "interne"
      ? [
          { lib: "Agents surveillés", val: comptes.agents, sous: "déclarés par Orbis Pay" },
          {
            lib: "À traiter",
            val: comptes.aTraiter.interne,
            sous:
              comptes.aDecider.interne > 0
                ? `dont ${comptes.aDecider.interne} attend${comptes.aDecider.interne > 1 ? "ent" : ""} votre décision`
                : "aucune action en attente",
            alerte: comptes.aDecider.interne > 0,
          },
          {
            lib: "Actions arrêtées",
            val: comptes.actionsArretees,
            sous: comptes.actionsVues ? `sur les ${comptes.actionsVues} dernières actions` : "aucune action récente",
          },
        ]
      : [
          { lib: "Postes protégés", val: comptes.postes, sous: "salariés sous pseudonyme" },
          { lib: "Arrêtés à temps", val: mesures?.gestes_humains?.arretes ?? 0, sous: "le salarié a annulé après l'alerte" },
          {
            lib: "À traiter",
            val: comptes.aTraiter.humain,
            sous: "dossiers remontés au SOC",
            alerte: comptes.aTraiter.humain > 0,
          },
        ];

  const ecrireRegle = (a: AgentInventaire) => {
    const sujet = a.libelle ? majuscule(a.libelle) : a.nom;
    regles.current?.preremplir(`${sujet} ne doit jamais `);
  };

  return (
    <>
      <SegmentsPiliers pilier={pilier} setPilier={setPilier} comptes={comptes.aTraiter} titreCompte="à traiter" />

      <div className="grille-compteurs">
        {compteurs.map((c) => (
          <div key={c.lib} className={`compteur ${c.alerte ? "alerte" : ""}`}>
            <div className="lib">{c.lib}</div>
            <div className="val">{c.val}</div>
            <div className="sous">{c.sous}</div>
          </div>
        ))}
      </div>

      {pilier === "interne" ? (
        <>
          <section className="panneau" aria-labelledby="inv-titre">
            <div className="titre">
              <span id="inv-titre">Les agents d'Orbis Pay</span>
              <span className="droite">ceux qui attendent une décision en premier</span>
            </div>
            <div className="corps">
              {chargement ? (
                <Spinner texte="Connexion…" />
              ) : (
                <InventaireAgents
                  inventaire={inventaire.filter((a) => a.contexte !== "poste")}
                  sessions={sessions}
                  incidents={incidents}
                  ouvrirIncident={ouvrirIncident}
                  ecrireRegle={ecrireRegle}
                />
              )}
            </div>
          </section>
          <AgentsPostes inventaire={inventaire} />
          <FilAgents activite={activite} incidents={incidents} chargement={chargement} ouvrirIncident={ouvrirIncident} />
          <PanneauRegles ref={regles} />
        </>
      ) : (
        <section className="panneau" aria-labelledby="postes-titre">
          <div className="titre">
            <span id="postes-titre">Les postes</span>
            <span className="droite">sous pseudonyme</span>
          </div>
          {chargement ? (
            <Spinner texte="Connexion…" />
          ) : (
            <ListePostes sessions={sessions} incidents={incidents} ouvrirIncident={ouvrirIncident} />
          )}
        </section>
      )}
    </>
  );
}

type Compteur = { lib: string; val: number; sous: string; alerte?: boolean };

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
  const enAttente = useMemo(() => new Set(incidents.filter(attendDecision).map((i) => i.id)), [incidents]);
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
        <div className="vide">Aucune action d'agent pour l'instant. Chaque appel d'outil s'affichera ici.</div>
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
  const { sessions, activite } = useDonnees();
  const outilsSession = a.agent ? [] : activite.filter((x) => x.session_id === a.session_id).map((x) => x.outil);
  const v = VERDICT[a.verdict] ?? VERDICT.autorise;
  return (
    <li className={`fil-ligne v-${v.cls}`}>
      <time className="fil-heure" dateTime={a.heure}>{heure(a.heure)}</time>
      <span className={`fil-verdict v-${v.cls}`}>
        <span className="fil-pt" />
        {v.lib}
      </span>
      <span className="fil-texte" title={a.raison ? desarmer(decoder(a.raison)) : undefined}>
        <strong>{nomAgentPour(a.agent, a.session_id, sessions, outilsSession)}</strong> veut {libelleOutil(a.outil)}
        <span className="fil-raison"> · {raisonActivite(a, enAttente)}</span>
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
