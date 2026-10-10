// Intégrations vues depuis la console, sans nouvelle entrée de menu :
// - « Alertes et SMS » dans le menu Exporter d'un dossier : qui serait prévenu,
//   par quel canal, avec quel texte (le SMS n'est jamais envoyé), et la ligne
//   CEF transmise au SIEM (GET /api/incidents/{id}/notifications) ;
// - « Résumé du lundi » dans Mesures : le mail de la semaine en aperçu, jamais
//   envoyé (GET /api/resume-hebdo).

import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useDonnees } from "../api/store";
import { Icone } from "../agent/icones";
import "./integrations.css";

type Envoi = {
  id: string;
  horodatage: string;
  canal: "webhook" | "sms";
  regle: string;
  destinataire: "soc" | "validation";
  destinataire_libelle?: string;
  a?: string | null;
  format?: string;
  texte: string;
  statut: string;
  raison?: string;
  encodage?: string;
  segments?: number;
  caracteres?: number;
};

type ApercuNotifications = {
  incident_id: string;
  regle: "menace" | "attente" | "personne" | string;
  raison: string;
  prevus: Envoi[];
  envoyes: Envoi[];
  syslog: { configure: boolean; cible: string | null; erreur: string | null; ligne_cef: string };
  rien_ne_part: string;
};

const REGLES: Record<string, string> = {
  menace: "Menace : l'équipe sécurité est prévenue",
  attente: "En attente du relecteur",
  personne: "Personne n'est prévenu",
};

const STATUTS: Record<string, string> = {
  simule: "simulé, jamais envoyé",
  coupe: "SMS coupé",
  pret: "prêt à partir",
  non_configure: "webhook non configuré",
  envoyee: "envoyé",
  en_cours: "en cours d'envoi",
  non_envoyee: "non envoyé, pas d'URL",
  refusee: "refusé par le destinataire",
  echec: "échec réseau",
  limitee: "plafond atteint",
  configuration_invalide: "configuration invalide",
};

function heure(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
}

// Fenêtre modale : focus gardé dedans, Échap ferme, le défilement de la page est bloqué.
function Modale({ sourcil, titre, fermer, large, children }: {
  sourcil: string;
  titre: string;
  fermer: () => void;
  large?: boolean;
  children: ReactNode;
}) {
  const boite = useRef<HTMLDivElement>(null);
  const bouton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const precedent = document.activeElement as HTMLElement | null;
    bouton.current?.focus();
    const touche = (e: KeyboardEvent) => {
      if (e.key === "Escape") fermer();
      if (e.key === "Tab" && boite.current) {
        const f = boite.current.querySelectorAll<HTMLElement>("button, a[href], iframe, [tabindex='0']");
        const premier = f[0];
        const dernier = f[f.length - 1];
        if (e.shiftKey && document.activeElement === premier) {
          e.preventDefault();
          dernier?.focus();
        } else if (!e.shiftKey && document.activeElement === dernier) {
          e.preventDefault();
          premier?.focus();
        }
      }
    };
    document.addEventListener("keydown", touche);
    const ancien = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", touche);
      document.body.style.overflow = ancien;
      precedent?.focus?.();
    };
  }, [fermer]);
  // Rendue sous <body> : un panneau animé (transform) piégerait le fond fixe.
  return createPortal(
    <div className="modale-fond" onMouseDown={fermer}>
      <div
        className={`modale integ-modale${large ? " integ-large" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="integ-titre"
        ref={boite}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <header className="modale-tete">
          <div>
            <span className="ag-sourcil">{sourcil}</span>
            <h3 id="integ-titre">{titre}</h3>
          </div>
          <button type="button" className="modale-fermer" onClick={fermer} ref={bouton} aria-label="Fermer">
            <Icone nom="fermer" taille={16} />
          </button>
        </header>
        {children}
      </div>
    </div>,
    document.body
  );
}

function CarteEnvoi({ e }: { e: Envoi }) {
  const qui = e.destinataire === "validation" ? "Validateur métier" : "Équipe sécurité";
  if (e.canal === "sms") {
    return (
      <article className="integ-envoi">
        <div className="integ-envoi-tete">
          <span className="integ-canal">SMS</span>
          <span className="integ-qui">{qui}{e.a ? ` · ${e.a}` : ""}</span>
          <span className={`integ-statut s-${e.statut}`}>{STATUTS[e.statut] ?? e.statut}</span>
        </div>
        <p className="integ-bulle">{e.texte}</p>
        <p className="integ-meta">
          {e.segments ? `${e.segments} SMS · ${e.caracteres} caractères ${e.encodage}` : ""}
          {e.statut === "simule" ? " · écrit dans le journal de démo, rien ne part" : ""}
        </p>
      </article>
    );
  }
  return (
    <article className="integ-envoi">
      <div className="integ-envoi-tete">
        <span className="integ-canal">Webhook{e.format ? ` ${e.format === "json" ? "JSON" : e.format === "teams" ? "Teams" : "Slack"}` : ""}</span>
        <span className="integ-qui">{qui}</span>
        <span className={`integ-statut s-${e.statut}`}>{STATUTS[e.statut] ?? e.statut}</span>
      </div>
      <p className="integ-texte">{e.texte}</p>
    </article>
  );
}

export function ModaleAlertes({ incidentId, fermer }: { incidentId: string; fermer: () => void }) {
  const [a, setA] = useState<ApercuNotifications | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  useEffect(() => {
    let vivant = true;
    fetch(`/api/incidents/${encodeURIComponent(incidentId)}/notifications`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((j) => vivant && setA(j))
      .catch((e) => vivant && setErreur(`Aperçu indisponible (${e.message}).`));
    return () => {
      vivant = false;
    };
  }, [incidentId]);

  return (
    <Modale sourcil={`Dossier ${incidentId}`} titre="Qui est prévenu" fermer={fermer}>
      <div className="integ-corps">
        {erreur && <p className="decision-erreur">{erreur}</p>}
        {!a && !erreur && <p className="integ-meta">Lecture…</p>}
        {a && (
          <>
            <p className={`integ-regle r-${a.regle}`}>
              <span className="integ-point" aria-hidden="true" />
              <strong>{REGLES[a.regle] ?? a.regle}.</strong> {a.raison}
            </p>
            {a.prevus.length > 0 && (
              <section>
                <h4 className="integ-h4">Ce qui partirait</h4>
                {a.prevus.map((e) => (
                  <CarteEnvoi key={e.id} e={e} />
                ))}
              </section>
            )}
            {a.envoyes.length > 0 && (
              <section>
                <h4 className="integ-h4">Déjà parti</h4>
                <ul className="integ-liste">
                  {a.envoyes.map((e) => (
                    <li key={e.id}>
                      {heure(e.horodatage)} · {e.canal === "sms" ? "SMS" : "Webhook"} ·{" "}
                      {e.destinataire === "validation" ? "validateur métier" : "équipe sécurité"} ·{" "}
                      {STATUTS[e.statut] ?? e.statut}
                    </li>
                  ))}
                </ul>
              </section>
            )}
            <section>
              <h4 className="integ-h4">
                Transfert vers le SIEM{" "}
                <span className="integ-meta">
                  {a.syslog.configure ? `syslog ${a.syslog.cible}` : "syslog non configuré (DEDALE_SYSLOG)"}
                </span>
              </h4>
              <pre className="integ-cef">{a.syslog.ligne_cef}</pre>
            </section>
            <p className="integ-note">{a.rien_ne_part}</p>
          </>
        )}
      </div>
    </Modale>
  );
}

export function ResumeLundi() {
  const { mode } = useDonnees();
  const [ouvert, setOuvert] = useState(false);
  const enDirect = mode === "live";
  return (
    <section className="panneau integ-resume">
      <div className="titre">
        Résumé du lundi
        <span className="droite">aperçu, jamais envoyé</span>
      </div>
      <div className="corps integ-resume-corps">
        <p>
          Le mail que la direction recevrait lundi matin : les menaces arrêtées, les gestes retenus et leur
          issue, les agents à surveiller, les règles qui ont joué. Une phrase par point, à lire en deux minutes.
        </p>
        <button type="button" className="export-btn" disabled={!enDirect} onClick={() => setOuvert(true)}>
          <Icone nom="oeil" taille={15} />
          Voir le mail
        </button>
        {!enDirect && <p className="integ-meta">Disponible quand le backend répond.</p>}
      </div>
      {ouvert && (
        <Modale sourcil="Résumé du lundi · aperçu" titre="Votre semaine avec sAIfe" fermer={() => setOuvert(false)} large>
          <iframe className="integ-iframe" title="Aperçu du mail du lundi" src="/api/resume-hebdo" sandbox="" />
          <p className="integ-note integ-note-bas">Aperçu : ce mail n'est envoyé à personne.</p>
        </Modale>
      )}
    </section>
  );
}
