// Outils du dossier, en haut à droite d'un incident : l'état du journal scellé
// (« Journal intact » ou « altéré à l'étape N ») et un seul menu d'export
// (rapport à imprimer, document ECS pour le SIEM, règle Sigma).

import { useEffect, useRef, useState } from "react";
import { useDonnees } from "../api/store";
import type { Incident, Verification } from "../types";
import { Icone } from "./icones";

// Signatures ajoutées par le backend (CONTRATS.md, « journal signé, en ajout
// seul, ancrage Avalanche en exploration »). Absentes du mock : le badge s'en passe.
type VerificationSignee = Verification & {
  signatures?: { valides: number; falsifiees: number };
};

// L'ancrage sur Avalanche est une voie d'exploration : aucune ancre n'est publiée.
// Le badge ne montre que l'intégrité vérifiée en local et le dit dans l'infobulle.
const EXPLORATION = "Ancrage Avalanche : en exploration, aucune empreinte publiée.";

// « altérée à l'étape 3 : champ motif modifié » devient « altéré à l'étape 3 » ;
// « altérée : en-tête de l'incident, champ statut modifié », « altéré : en-tête de l'incident ».
function verdictCourt(verdict: string): string {
  const [tete, ...reste] = verdict.split(" : ");
  const court = tete === "altérée" && reste.length ? `altéré : ${reste.join(" : ").split(", ")[0]}` : tete;
  return court.replace("altérée", "altéré");
}

export function BadgeIntegrite({ incident }: { incident: Incident }) {
  const { getVerification } = useDonnees();
  const [v, setV] = useState<VerificationSignee | null>(null);
  const version = `${incident.id}|${incident.decisions?.length ?? 0}|${incident.chaine?.length ?? 0}|${incident.journal_console?.length ?? 0}`;

  useEffect(() => {
    let vivant = true;
    // Le backend laisse d'abord son écrivain vider la file : on attend un peu.
    const t = window.setTimeout(() => {
      getVerification(incident.id)
        .then((r) => vivant && setV(r as VerificationSignee))
        .catch(() => vivant && setV(null));
    }, 600);
    return () => {
      vivant = false;
      window.clearTimeout(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version, getVerification]);

  if (!v) return null;
  const intact = v.statut === "intacte";
  const altere = v.statut === "alteree";
  // « Journal altéré à l'étape 3 » : le champ modifié et la raison vont dans l'infobulle.
  const lib = intact
    ? "Journal intact"
    : altere
      ? `Journal ${verdictCourt(v.verdict)}`
      : v.statut === "non_persiste"
        ? "Journal en cours d'écriture"
        : "Antérieur au scellement";
  const n = v.signatures?.valides ?? 0;
  const signe = n ? ` ${n} entrée${n > 1 ? "s" : ""} signée${n > 1 ? "s" : ""} par leur émetteur.` : "";
  const titre = intact
    ? `Chaque étape, chaque acte et chaque décision ont été relus dans la base : aucun n'a changé.${signe}${v.sceau ? ` Sceau ${v.sceau.slice(0, 16)}…` : ""} ${EXPLORATION}`
    : altere
      ? `${v.verdict.charAt(0).toUpperCase()}${v.verdict.slice(1)}.${v.raison ? ` ${v.raison}.` : ""}`
      : "Ce dossier n'a pas encore d'empreinte vérifiable.";
  return (
    <span className={`integrite ${intact ? "i-ok" : altere ? "i-alerte" : "i-neutre"}`} title={titre}>
      <Icone nom="sceau" taille={14} />
      {lib}
    </span>
  );
}

async function telecharger(url: string, nom: string, type: string): Promise<void> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`Export refusé (HTTP ${r.status}).`);
  const brut = type === "application/json" ? JSON.stringify(await r.json(), null, 2) : await r.text();
  const lien = document.createElement("a");
  lien.href = URL.createObjectURL(new Blob([brut], { type }));
  lien.download = nom;
  document.body.appendChild(lien);
  lien.click();
  lien.remove();
  window.setTimeout(() => URL.revokeObjectURL(lien.href), 2000);
}

export function MenuExport({ incident }: { incident: Incident }) {
  const { mode } = useDonnees();
  const [ouvert, setOuvert] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const zone = useRef<HTMLDivElement>(null);
  const bouton = useRef<HTMLButtonElement>(null);
  const id = encodeURIComponent(incident.id);
  const horsLigne = mode !== "live";

  useEffect(() => {
    if (!ouvert) return;
    const dehors = (e: MouseEvent) => {
      if (zone.current && !zone.current.contains(e.target as Node)) setOuvert(false);
    };
    const echap = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOuvert(false);
        bouton.current?.focus();
      }
    };
    document.addEventListener("mousedown", dehors);
    document.addEventListener("keydown", echap);
    return () => {
      document.removeEventListener("mousedown", dehors);
      document.removeEventListener("keydown", echap);
    };
  }, [ouvert]);

  const lancer = (f: () => Promise<void> | void) => async () => {
    setErreur(null);
    try {
      await f();
      setOuvert(false);
    } catch (e) {
      setErreur(e instanceof Error ? e.message : "Export impossible.");
    }
  };

  return (
    <div className="export" ref={zone}>
      <button
        type="button"
        ref={bouton}
        className="export-btn"
        aria-haspopup="menu"
        aria-expanded={ouvert}
        onClick={() => setOuvert((v) => !v)}
      >
        <Icone nom="exporter" taille={15} />
        Exporter
      </button>
      {ouvert && (
        <div className="export-menu" role="menu">
          <button
            type="button"
            role="menuitem"
            disabled={horsLigne}
            onClick={lancer(() => {
              window.open(`/api/incidents/${id}/rapport`, "_blank", "noopener");
            })}
          >
            <span className="export-lib">Rapport</span>
            <span className="export-aide">une page A4, à imprimer en PDF</span>
          </button>
          <button
            type="button"
            role="menuitem"
            disabled={horsLigne}
            onClick={lancer(() => telecharger(`/api/incidents/${id}/export?format=ecs`, `${incident.id}-ecs.json`, "application/json"))}
          >
            <span className="export-lib">Export ECS</span>
            <span className="export-aide">les événements, pour Elastic ou un autre SIEM</span>
          </button>
          <button
            type="button"
            role="menuitem"
            disabled={horsLigne}
            onClick={lancer(() => telecharger(`/api/incidents/${id}/export?format=sigma`, `${incident.id}.yml`, "application/x-yaml"))}
          >
            <span className="export-lib">Règle Sigma</span>
            <span className="export-aide">pour repérer le même schéma dans vos journaux</span>
          </button>
          {horsLigne && <p className="export-note">Disponible quand le backend répond.</p>}
          {erreur && <p className="decision-erreur">{erreur}</p>}
        </div>
      )}
    </div>
  );
}
