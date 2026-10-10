// Encadré « Ce qui s'est passé » : deux ou trois phrases, le niveau de
// certitude et la décision conseillée. Les phrases viennent du copilote du
// backend (GET /api/incidents/{id}/synthese) ; si la route ne répond pas, la
// console écrit un résumé à partir de ce qu'elle sait déjà.

import { useEffect, useState } from "react";
import { useDonnees } from "../api/store";
import type { Incident, RaisonConfiance, Synthese } from "../types";
import { TexteCanary } from "../ui/Canary";
import { ACTION_CONSEILLEE, libelleDroit, sansCodes } from "../ui/mots";

export function useSynthese(incident: Incident): { synthese: Synthese | null; prete: boolean } {
  const { getSynthese } = useDonnees();
  const [etat, setEtat] = useState<{ id: string; synthese: Synthese | null; prete: boolean }>({
    id: incident.id,
    synthese: null,
    prete: false,
  });
  // On relit la synthèse quand l'incident change d'état (décision, correctif).
  const version = `${incident.id}|${incident.etat}|${incident.statut}|${incident.decisions?.length ?? 0}|${incident.correctifs?.length ?? 0}|${incident.droits_retirables?.length ?? 0}`;
  useEffect(() => {
    let vivant = true;
    getSynthese(incident.id)
      .then((s) => vivant && setEtat({ id: incident.id, synthese: s?.phrases?.length ? s : null, prete: true }))
      .catch(() => vivant && setEtat({ id: incident.id, synthese: null, prete: true }));
    return () => {
      vivant = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version, getSynthese]);
  if (etat.id !== incident.id) return { synthese: null, prete: false };
  return { synthese: etat.synthese, prete: etat.prete };
}

// Raisons du niveau de certitude, en clair. [effet positif, effet négatif].
const RAISONS: Record<string, [string, string?]> = {
  canari: ["Il a touché un canary : un humain ne le fait jamais."],
  consigne: ["Une instruction cachée a été trouvée dans ce qu'il a lu."],
  hors_jeton: ["Il a demandé un accès que sa tâche ne prévoit pas."],
  sortie: ["Il a essayé d'envoyer des données vers l'extérieur."],
  classement: ["Son comportement ressemble à celui d'un agent détourné."],
  concordance: ["Plusieurs signes vont dans le même sens.", "Un seul signe : à confirmer."],
  maillons: ["Toutes les étapes ont été observées.", "Peu d'étapes observées."],
  passe_outre: ["Le salarié a été prévenu et a continué quand même."],
  action_risquee: ["Le geste était risqué en lui-même."],
  consequence: ["Le geste a eu une suite."],
  entree_absente: ["", "On ne sait pas ce que l'agent a lu en premier."],
  decision_absente: ["Personne n'a encore décidé.", "Personne n'a encore décidé."],
  evenements_perdus: ["", "Des événements manquent dans le journal."],
  contexte_absent: ["", "Le contexte du geste manque."],
};

function raisonClaire(r: RaisonConfiance): string {
  const [plus, moins] = RAISONS[r.code] ?? [];
  const t = r.effet < 0 ? moins || plus : plus || moins;
  return t || sansCodes(r.texte);
}

function Certitude({ score }: { score: number }) {
  const pct = Math.round(Math.min(1, Math.max(0, score > 1 ? score / 100 : score)) * 100);
  const cls = pct >= 75 ? "haute" : pct >= 50 ? "moyenne" : "basse";
  return (
    <div className={`syn-certitude c-${cls}`} title="Certitude calculée par Dédale à partir des signes observés">
      <span className="syn-certitude-val">Sûr à {pct} %</span>
      <span className="syn-jauge" aria-hidden="true">
        <span style={{ transform: `scaleX(${pct / 100})` }} />
      </span>
    </div>
  );
}

export function SyntheseBloc({
  synthese,
  prete,
  repli,
}: {
  synthese: Synthese | null;
  prete: boolean;
  repli: string[];
}) {
  const phrases = synthese?.phrases?.map((p) => p.texte) ?? (prete ? repli : []);
  const conf = synthese?.confiance;
  const conseil = synthese?.decision_recommandee;
  const correctif = synthese?.correctif_suggere;
  const raisons = [...(conf?.raisons ?? []), ...(conf?.manquants ?? [])].filter((r) => raisonClaire(r));
  const action = conseil ? ACTION_CONSEILLEE[conseil.action] ?? conseil.action : null;

  return (
    <section className="syn" aria-labelledby="syn-titre">
      <div className="syn-tete">
        <h3 id="syn-titre" className="syn-titre">Ce qui s'est passé</h3>
        {conf && typeof conf.score === "number" && <Certitude score={conf.score} />}
      </div>
      {phrases.length === 0 ? (
        <p className="syn-attente">Lecture du dossier…</p>
      ) : (
        <div className="syn-phrases">
          {phrases.map((p, i) => (
            <p key={i}>{p}</p>
          ))}
        </div>
      )}
      {(action || correctif) && (
        <div className="syn-conseil">
          <span className="syn-conseil-lib">Décision conseillée</span>
          <span className="syn-conseil-val">
            {action}
            {conseil?.deja_appliquee && <em> (déjà fait)</em>}
            {correctif && (
              <>
                {action ? " · puis retirer" : "Retirer"} l'accès « {libelleDroit(correctif.droit, correctif.libelle)} »
              </>
            )}
          </span>
        </div>
      )}
      {raisons.length > 0 && (
        <details className="syn-raisons">
          <summary>Pourquoi ce niveau de certitude</summary>
          <ul>
            {raisons.map((r, i) => (
              <li key={i} className={r.effet < 0 ? "moins" : "plus"} title={sansCodes(r.texte)}>
                <TexteCanary texte={raisonClaire(r)} />
              </li>
            ))}
          </ul>
          <p className="syn-rappel">Vous décidez : Dédale n'agit jamais seul.</p>
        </details>
      )}
    </section>
  );
}
