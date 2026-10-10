// Avis du relecteur IA sur un incident (GET /api/incidents/{id}/tri) : priorité,
// décision proposée, motif, confiance. Une ligne discrète en haut du panneau de
// décision : un avis, jamais une décision.

import { useEffect, useState } from "react";
import { useDonnees } from "../api/store";
import type { Incident, PreTri } from "../types";
import { ACTION_CONSEILLEE, decoder } from "../ui/mots";

const PRIORITE: Record<string, string> = { haute: "priorité haute", normale: "priorité normale", basse: "priorité basse" };

export function AvisRelecteur({ incident }: { incident: Incident }) {
  const { getTri } = useDonnees();
  const [tri, setTri] = useState<PreTri | null>(null);
  const version = `${incident.id}|${incident.type}|${incident.gravite}|${incident.decisions?.length ?? 0}`;

  useEffect(() => {
    let vivant = true;
    setTri(null);
    getTri(incident.id)
      .then((t) => vivant && setTri(t))
      .catch(() => vivant && setTri(null));
    return () => {
      vivant = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version, getTri]);

  if (!tri || !tri.decision_proposee) return null;
  const qui = tri.tranche_par && tri.tranche_par !== "règles" ? `relecteur IA (${tri.tranche_par})` : "règles du relecteur";
  const action = (ACTION_CONSEILLEE[tri.decision_proposee] ?? tri.decision_proposee).toLowerCase();
  const confiance = typeof tri.confiance === "number" ? `${Math.round(tri.confiance * 100)} %` : null;
  const motif = tri.motif_soc ?? tri.motif;
  return (
    <p className={`avis-relecteur ${tri.doute ? "doute" : ""}`}>
      <span className="avis-lib">
        Pré-tri · {qui}
        {tri.statut === "en_cours" ? ", en cours" : ""}
      </span>
      <span className="avis-val">
        {PRIORITE[tri.priorite ?? ""] ?? "priorité inconnue"} · propose de {action}
        {confiance ? ` · sûr à ${confiance}` : ""}
        {tri.doute ? " · à vérifier" : ""}
      </span>
      {motif && <span className="avis-motif">{decoder(motif)}</span>}
    </p>
  );
}
