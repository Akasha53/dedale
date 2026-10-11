import { useMemo } from "react";
import { useDonnees } from "../api/store";
import type { DureeMesuree, PointSerie } from "../types";
import { compter } from "../ui/compteurs";
import { Spinner } from "../ui/primitives";
import { ResumeLundi } from "../integrations/Integrations";

// Durée lisible, avec la virgule française : « 120 ms », « 2,4 s », « 1 h 33 min ».
function duree(ms: number | null | undefined): string {
  if (ms == null || !Number.isFinite(ms)) return "";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(s < 10 ? 1 : 0).replace(".", ",")} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ${String(Math.round(s % 60)).padStart(2, "0")} s`;
  return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")} min`;
}

function KpiDuree({ lib, d, vide }: { lib: string; d?: DureeMesuree; vide: string }) {
  const ok = d && d.echantillons > 0 && d.mediane_ms != null;
  return (
    <div className="kpi">
      <div className="lib">{lib}</div>
      {ok ? (
        <>
          <div className="val">{duree(d!.mediane_ms)}</div>
          <div className="kpi-sous">
            médiane · moyenne {duree(d!.moyenne_ms)} · {d!.echantillons} mesure{d!.echantillons > 1 ? "s" : ""}
          </div>
        </>
      ) : (
        <div className="kpi-vide">{vide}</div>
      )}
    </div>
  );
}

// Accord en nombre à la française : singulier pour 0 et 1.
function nb(n: number, mot: string): string {
  return `${n} ${mot}${n > 1 ? "s" : ""}`;
}

function Kpi({ lib, val, sous, cls = "" }: { lib: string; val: string | number; sous?: string; cls?: string }) {
  return (
    <div className="kpi">
      <div className="lib">{lib}</div>
      <div className={`val ${cls}`}>{val}</div>
      {sous && <div className="kpi-sous">{sous}</div>}
    </div>
  );
}

function Barre({ lib, n, total, cls }: { lib: string; n: number; total: number; cls: string }) {
  const pct = total > 0 ? Math.round((n / total) * 100) : 0;
  return (
    <div className="mes-barre">
      <span className="mes-barre-lib">{lib}</span>
      <span className="mes-barre-piste" aria-hidden="true">
        <span className={`mes-barre-plein ${cls}`} style={{ transform: `scaleX(${total > 0 ? n / total : 0})` }} />
      </span>
      <span className="mes-barre-val">
        {n}
        <span className="mes-barre-pct"> · {pct} %</span>
      </span>
    </div>
  );
}

export function MesuresView() {
  const { mesures, chargement, sessions, incidents, inventaire, activite } = useDonnees();
  const comptes = useMemo(() => compter(incidents, sessions, inventaire, activite), [incidents, sessions, inventaire, activite]);

  if (chargement) return <Spinner />;
  if (!mesures) return <div className="vide">Mesures indisponibles : le backend ne répond pas.</div>;

  const m = mesures.matrice;
  const positifs = m ? m.vrais_positifs + m.faux_negatifs : 0;
  const negatifs = m ? m.faux_positifs + m.vrais_negatifs : 0;
  const pctDet = mesures.taux_detection == null ? null : Math.round(mesures.taux_detection * 100);
  const pctFP = mesures.faux_positifs == null ? null : Math.round(mesures.faux_positifs * 100);
  const gestes = mesures.gestes_humains;
  const autorisees = comptes.actionsVues - comptes.actionsArretees;
  const mesures_res = inventaire.filter((a) => a.resistance && a.resistance.essais);
  // Relecteur IA et sa mémoire (GET /api/mesures, bloc `relecteur`).
  const relecteur = (mesures as unknown as {
    relecteur?: { decisions: number; duree?: { mediane_ms: number | null }; memoire?: { entrees: number; renversements: number; decisions_appuyees: number } };
  }).relecteur;

  return (
    <>
      <p className="mes-intro">
        Les mêmes chiffres que dans les autres écrans. Les taux du banc ne prédisent pas une performance en production.
      </p>

      <div className="grille-mesures">
        <KpiDuree
          lib="Temps de détection"
          d={mesures.temps_detection}
          vide="Pas encore mesuré : il faut une session repérée comme agent détourné."
        />
        <KpiDuree
          lib="Temps de confinement"
          d={mesures.temps_confinement}
          vide="Pas encore mesuré : il faut un agent coupé après détection."
        />
        {pctDet == null ? (
          <div className="kpi">
            <div className="lib">Taux de détection</div>
            <div className="kpi-vide">Mesuré sur le trafic du banc seulement : aucun dans cette base.</div>
          </div>
        ) : (
          <Kpi lib="Taux de détection" val={`${pctDet} %`} sous={m ? `${m.vrais_positifs} sur ${positifs} sessions du banc` : undefined} cls="bon" />
        )}
        {pctFP == null ? (
          <div className="kpi">
            <div className="lib">Faux positifs</div>
            <div className="kpi-vide">Mesuré sur le trafic du banc seulement : aucun dans cette base.</div>
          </div>
        ) : (
          <Kpi
            lib="Faux positifs"
            val={`${pctFP} %`}
            sous={m ? `${m.faux_positifs} sur ${negatifs} sessions humaines ou scriptées` : undefined}
            cls={pctFP > 10 ? "att" : "bon"}
          />
        )}
      </div>

      <div className="grille-mesures">
        <Kpi lib="Agents surveillés" val={comptes.agents} sous="déclarés par Orbis Pay" />
        <Kpi lib="Postes protégés" val={comptes.postes} sous="sous pseudonyme" />
        <Kpi
          lib="Dossiers à traiter"
          val={comptes.aTraiter.interne + comptes.aTraiter.humain}
          sous={`${nb(comptes.aTraiter.interne, "agent")} · ${nb(comptes.aTraiter.humain, "salarié")}`}
          cls={comptes.aTraiter.interne + comptes.aTraiter.humain > 0 ? "att" : ""}
        />
        <Kpi
          lib="Dossiers réglés"
          val={comptes.regles.interne + comptes.regles.humain}
          sous={`${nb(comptes.regles.interne, "agent")} · ${nb(comptes.regles.humain, "salarié")}`}
        />
      </div>

      {relecteur && (
        <div className="grille-mesures">
          <Kpi
            lib="Relectures de sAIfe"
            val={relecteur.decisions}
            sous={relecteur.duree?.mediane_ms != null ? `médiane ${duree(relecteur.duree.mediane_ms)}` : "gestes critiques et pré-tris"}
          />
          <Kpi
            lib="Appuyées sur la mémoire"
            val={relecteur.memoire?.decisions_appuyees ?? 0}
            sous={`${nb(relecteur.memoire?.entrees ?? 0, "décision")} d'analyste en mémoire`}
          />
          <Kpi
            lib="Renversements"
            val={relecteur.memoire?.renversements ?? 0}
            sous="relecteur contredit par un analyste"
            cls={(relecteur.memoire?.renversements ?? 0) > 0 ? "att" : ""}
          />
        </div>
      )}

      <div className="graphes">
        <section className="panneau">
          <div className="titre">
            Actions des agents
            <span className="droite">{comptes.actionsVues ? `les ${comptes.actionsVues} dernières` : "aucune"}</span>
          </div>
          <div className="corps">
            {comptes.actionsVues === 0 ? (
              <div className="vide">Aucune action d'agent pour l'instant.</div>
            ) : (
              <>
                <Barre lib="Autorisées" n={autorisees} total={comptes.actionsVues} cls="b-neutre" />
                <Barre lib="Retenues ou refusées" n={comptes.actionsArretees} total={comptes.actionsVues} cls="b-ok" />
              </>
            )}
            {mesures_res.length > 0 && (
              <div className="mes-resistance">
                <p className="mes-sous-titre">Résistance aux contenus piégés · trafic synthétique</p>
                {mesures_res.map((a) => (
                  <Barre
                    key={a.id}
                    lib={a.nom}
                    n={(a.resistance!.essais ?? 0) - (a.resistance!.suivis ?? 0)}
                    total={a.resistance!.essais ?? 0}
                    cls={(a.resistance!.suivis ?? 0) > 0 ? "b-alerte" : "b-neutre"}
                  />
                ))}
              </div>
            )}
          </div>
        </section>

        <section className="panneau">
          <div className="titre">
            Gestes des salariés
            <span className="droite">{gestes?.total ? `${gestes.total} alertes affichées` : "aucune alerte"}</span>
          </div>
          <div className="corps">
            {!gestes || gestes.total === 0 ? (
              <div className="vide">Aucune alerte affichée sur un poste pour l'instant.</div>
            ) : (
              <>
                <Barre lib="Annulés après l'alerte" n={gestes.arretes} total={gestes.total} cls="b-ok" />
                <Barre lib="Continués malgré l'alerte" n={gestes.passes_outre} total={gestes.total} cls="b-alerte" />
              </>
            )}
            <p className="mes-note">
              {gestes?.signalements
                ? `${gestes.signalements} mail${gestes.signalements > 1 ? "s" : ""} signalé${gestes.signalements > 1 ? "s" : ""} par les salariés eux-mêmes.`
                : "Aucun mail signalé par les salariés pour l'instant."}
            </p>
          </div>
        </section>
      </div>

      <ResumeLundi />

      {pctDet != null && mesures.serie_detection.length >= 2 && (
        <section className="panneau">
          <div className="titre">
            Taux de détection au fil des sessions du banc
            <span className="droite">{mesures.serie_detection.length} sessions</span>
          </div>
          <div className="corps">
            <GrapheLigne points={mesures.serie_detection} />
          </div>
        </section>
      )}
    </>
  );
}

function GrapheLigne({ points }: { points: PointSerie[] }) {
  const W = 560;
  const H = 180;
  const P = 28;
  const max = 1; // taux 0..1
  const min = Math.max(0, Math.min(...points.map((p) => p.valeur)) - 0.1);
  const x = (i: number) => P + (i * (W - 2 * P)) / (points.length - 1);
  const y = (v: number) => H - P - ((v - min) / (max - min || 1)) * (H - 2 * P);
  const d = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(p.valeur)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Taux de détection au fil des sessions">
      {[0, 0.5, 1].map((g) => (
        <line key={g} x1={P} x2={W - P} y1={y(min + (max - min) * g)} y2={y(min + (max - min) * g)} stroke="var(--bord)" strokeDasharray="3 4" />
      ))}
      <path d={d} fill="none" stroke="var(--texte)" strokeWidth={2} strokeLinejoin="round" />
      {points.map((p, i) => (
        <circle key={i} cx={x(i)} cy={y(p.valeur)} r={3} fill="var(--texte)" />
      ))}
    </svg>
  );
}
