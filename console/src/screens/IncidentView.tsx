import { useEffect, useMemo, useRef, useState } from "react";
import { useDonnees } from "../api/store";
import type { ChoixSalarie, DecisionAction, Incident, MaillonChaine, Pilier } from "../types";
import { IncidentAgent } from "../agent/IncidentAgent";
import type { DetailMaillon } from "../agent/boiteNoire";
import { DetailEtape, Depliant } from "../agent/Depliant";
import { preuveInerte } from "../agent/preuve";
import { fusionnerRefs, lireRef } from "../agent/references";
import { SyntheseBloc, useSynthese } from "../agent/Synthese";
import { appartientPilier, BadgeChoixSalarie, heure, libelleType, PILIERS, SegmentsPiliers, Spinner } from "../ui/primitives";
import { decoder, estATraiter, etatIncident, GRAVITE, phraseSalarie, sansCodes, titreIncident } from "../ui/mots";

const PHASE_LIB: Record<string, string> = {
  entree: "Contexte",
  contexte: "Contexte",
  action_risquee: "Geste risqué",
  avertissement: "Alerte de Dédale",
  choix: "Choix du salarié",
  consequence: "Suite",
  sortie: "Suite",
  riposte: "Suite",
};

const VIDE_PILIER: Record<Pilier, string> = {
  humain: "Aucun incident salarié. Les postes sont calmes.",
  interne: "Aucun incident d'agent IA. Les agents d'Orbis Pay sont calmes.",
};

const ACTIONS_HUMAIN: { action: DecisionAction; lib: string; aide: string; cls: string }[] = [
  { action: "clore", lib: "Clore le dossier", aide: "Vous avez traité le cas : le dossier est fermé.", cls: "primaire" },
  { action: "ignorer", lib: "Classer sans suite", aide: "Fausse alerte : le dossier est fermé sans suite.", cls: "fantome" },
];

// Les plus récents d'abord. L'ordre ne dépend pas de l'état : une ligne qui
// se règle ne saute pas de place avant de disparaître.
function trier(incidents: Incident[]): Incident[] {
  return [...incidents].sort((a, b) => (b.ouvert_le ?? "").localeCompare(a.ouvert_le ?? ""));
}

export function IncidentView({
  incidentSel,
  setIncidentSel,
  pilier,
  setPilier,
}: {
  incidentSel: string | null;
  setIncidentSel: (id: string) => void;
  pilier: Pilier;
  setPilier: (p: Pilier) => void;
}) {
  const { incidents, getIncident, decider, chargement } = useDonnees();

  const incidentsVue = useMemo(
    () => trier(incidents.filter((i) => appartientPilier(i.source, pilier))),
    [incidents, pilier]
  );
  const comptes = useMemo(() => {
    const c = { humain: 0, interne: 0 } as Record<Pilier, number>;
    for (const p of PILIERS) c[p.id] = incidents.filter((i) => appartientPilier(i.source, p.id)).length;
    return c;
  }, [incidents]);

  // Par défaut, le premier incident à traiter. Le choix est aussitôt fixé :
  // un incident qui se règle reste affiché jusqu'à ce qu'on en ouvre un autre.
  const parDefaut = incidentsVue.find(estATraiter)?.id ?? null;
  const idCourant = useMemo(() => {
    if (incidentSel) return incidentsVue.some((i) => i.id === incidentSel) ? incidentSel : null;
    return parDefaut;
  }, [incidentSel, incidentsVue, parDefaut]);
  useEffect(() => {
    if (!incidentSel && parDefaut) setIncidentSel(parDefaut);
  }, [incidentSel, parDefaut, setIncidentSel]);

  const [detail, setDetail] = useState<Incident | null>(null);
  const [chargeDetail, setChargeDetail] = useState(false);
  const [erreurDetail, setErreurDetail] = useState<string | null>(null);
  const [decisionEnCours, setDecisionEnCours] = useState<DecisionAction | null>(null);
  const [erreurDecision, setErreurDecision] = useState<string | null>(null);

  useEffect(() => {
    if (!idCourant) {
      setDetail(null);
      return;
    }
    let vivant = true;
    // On part de la version de la liste, puis on récupère le détail à jour.
    setDetail(incidents.find((i) => i.id === idCourant) ?? null);
    setErreurDetail(null);
    setErreurDecision(null);
    setChargeDetail(true);
    getIncident(idCourant)
      .then((d) => vivant && setDetail(d))
      .catch(() => vivant && setErreurDetail("Le détail n'a pas pu être actualisé. Dernières données disponibles affichées."))
      .finally(() => vivant && setChargeDetail(false));
    return () => {
      vivant = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idCourant, getIncident]);

  // Le flux et le rafraîchissement mettent la liste à jour (décision, action
  // libérée, droit retiré). Quand l'incident courant change, on relit son détail.
  const versionListe = useMemo(() => {
    const i = incidents.find((x) => x.id === idCourant);
    return i
      ? `${i.etat}|${i.statut}|${i.chaine?.length ?? 0}|${i.decisions?.length ?? 0}|${i.correctifs?.length ?? 0}|${i.droits_retirables?.length ?? 0}`
      : "";
  }, [incidents, idCourant]);
  const versionVue = useRef("");
  useEffect(() => {
    if (!idCourant || !versionListe) return;
    const precedente = versionVue.current;
    versionVue.current = `${idCourant}#${versionListe}`;
    if (!precedente.startsWith(`${idCourant}#`) || precedente === versionVue.current) return;
    let vivant = true;
    getIncident(idCourant)
      .then((d) => vivant && setDetail(d))
      .catch(() => undefined);
    return () => {
      vivant = false;
    };
  }, [idCourant, versionListe, getIncident]);

  const trancher = async (action: DecisionAction) => {
    if (!idCourant || decisionEnCours) return;
    setDecisionEnCours(action);
    setErreurDecision(null);
    try {
      const resultat = await decider(idCourant, action, "analyste-soc");
      setDetail(resultat);
      try {
        setDetail(await getIncident(idCourant));
      } catch {
        // La réponse de décision contient déjà le nouvel état.
      }
    } catch (e) {
      setErreurDecision(e instanceof Error ? e.message : "La décision n'a pas pu être envoyée.");
      try {
        setDetail(await getIncident(idCourant));
      } catch {
        // État incertain : le message reste visible et aucun succès n'est supposé.
      }
    } finally {
      setDecisionEnCours(null);
    }
  };

  if (chargement) return <Spinner />;

  const segments = <SegmentsPiliers pilier={pilier} setPilier={setPilier} comptes={comptes} />;

  if (incidentSel && !idCourant)
    return (
      <>
        {segments}
        {incidents.some((i) => i.id === incidentSel) ? (
          <Spinner texte="Ouverture de l'incident…" />
        ) : (
          <div className="vide" role="status">Cet incident n'est plus dans la liste.</div>
        )}
      </>
    );

  if (incidentsVue.length === 0)
    return (
      <>
        {segments}
        <div className="vide">{VIDE_PILIER[pilier]}</div>
      </>
    );

  return (
    <>
      {segments}
      <ListeIncidents key={pilier} incidents={incidentsVue} courant={idCourant} choisir={setIncidentSel} />

      {erreurDetail && <div className="decision-erreur" role="alert">{erreurDetail}</div>}
      {!idCourant ? null : !detail || detail.id !== idCourant ? (
        <Spinner />
      ) : estIncidentAgent(detail) ? (
        <IncidentAgent
          incident={detail}
          majEnCours={chargeDetail}
          decisionEnCours={decisionEnCours}
          erreurDecision={erreurDecision}
          trancher={(a) => void trancher(a)}
        />
      ) : (
        <IncidentSalarie
          incident={detail}
          decisionEnCours={decisionEnCours}
          erreurDecision={erreurDecision}
          trancher={(a) => void trancher(a)}
        />
      )}
    </>
  );
}

// ---------- liste des incidents ----------

// Durées du départ d'une ligne réglée : barrée, puis repliée.
const BARRE_MS = 3600;
const REPLI_MS = 450;

// La liste ne montre que ce qui reste à traiter. Une ligne qui vient d'être
// réglée se barre quelques secondes, puis se replie et disparaît. Les
// incidents déjà réglés se rangent sous « réglés (n) ».
function ListeIncidents({
  incidents,
  courant,
  choisir,
}: {
  incidents: Incident[];
  courant: string | null;
  choisir: (id: string) => void;
}) {
  const [sortants, setSortants] = useState<Record<string, "barre" | "repli">>({});
  const [voirRegles, setVoirRegles] = useState(false);
  const precedents = useRef<Set<string> | null>(null);
  const minuteurs = useRef<ReturnType<typeof setTimeout>[]>([]);
  useEffect(() => () => minuteurs.current.forEach(clearTimeout), []);

  const aTraiter = incidents.filter(estATraiter);
  const cleATraiter = aTraiter.map((i) => i.id).join("|");

  useEffect(() => {
    const actuels = new Set(aTraiter.map((i) => i.id));
    const avant = precedents.current;
    precedents.current = actuels;
    if (!avant) return; // premier rendu : rien ne part
    const partis = [...avant].filter((id) => !actuels.has(id) && incidents.some((i) => i.id === id));
    if (partis.length === 0) return;
    setSortants((s) => {
      const c = { ...s };
      for (const id of partis) c[id] = "barre";
      return c;
    });
    for (const id of partis) {
      minuteurs.current.push(
        setTimeout(() => setSortants((s) => (s[id] ? { ...s, [id]: "repli" } : s)), BARRE_MS),
        setTimeout(
          () =>
            setSortants((s) => {
              const c = { ...s };
              delete c[id];
              return c;
            }),
          BARRE_MS + REPLI_MS
        )
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cleATraiter]);

  const affiches = incidents.filter((i) => estATraiter(i) || sortants[i.id]);
  const regles = incidents.filter((i) => !estATraiter(i) && !sortants[i.id]);

  return (
    <section className="panneau liste-inc" aria-labelledby="liste-inc-titre">
      <div className="titre">
        <span id="liste-inc-titre" aria-live="polite">
          {aTraiter.length === 0
            ? "Rien à traiter"
            : `${aTraiter.length} incident${aTraiter.length > 1 ? "s" : ""} à traiter`}
        </span>
        {regles.length > 0 && (
          <button
            type="button"
            className="liste-regles-btn"
            aria-expanded={voirRegles}
            onClick={() => setVoirRegles((v) => !v)}
          >
            réglés ({regles.length})
          </button>
        )}
      </div>
      {affiches.length > 0 && (
        <ul className="liste-inc-lignes">
          {affiches.map((i) => (
            <LigneIncident
              key={i.id}
              i={i}
              actif={i.id === courant}
              sortie={sortants[i.id]}
              choisir={choisir}
            />
          ))}
        </ul>
      )}
      {voirRegles && regles.length > 0 && (
        <ul className="liste-inc-lignes liste-regles" aria-label="Incidents réglés">
          {regles.map((i) => (
            <LigneIncident key={i.id} i={i} actif={i.id === courant} choisir={choisir} discret />
          ))}
        </ul>
      )}
    </section>
  );
}

function LigneIncident({
  i,
  actif,
  sortie,
  discret,
  choisir,
}: {
  i: Incident;
  actif: boolean;
  sortie?: "barre" | "repli";
  discret?: boolean;
  choisir: (id: string) => void;
}) {
  const e = etatIncident(i);
  return (
    <li className={`inc-item ${sortie ? `sortie-${sortie}` : ""}`}>
      <div className="inc-item-interieur">
        <button
          type="button"
          className={`inc-ligne ${actif ? "actif" : ""} ${sortie ? "regle" : ""} ${discret ? "discret" : ""}`}
          aria-current={actif ? "true" : undefined}
          onClick={() => choisir(i.id)}
          tabIndex={sortie === "repli" ? -1 : undefined}
        >
          <span className={`inc-point e-${e.cls}`} aria-hidden="true" />
          <span className="inc-titre">{titreIncident(i)}</span>
          <span className="inc-heure">{heure(i.ouvert_le).slice(0, 5)}</span>
          <span className={`inc-etat e-${e.cls}`}>{e.lib}</span>
        </button>
      </div>
    </li>
  );
}

// ---------- incident salarié ----------

// Agent IA interne : écran dédié. Un incident salarié n'y passe jamais.
function estIncidentAgent(inc: Incident): boolean {
  return !estIncidentHumain(inc) && (inc.source === "interne" || (inc.type ?? "").startsWith("interne_"));
}

function estIncidentHumain(inc: Incident): boolean {
  return inc.source === "humain" || inc.source === "physique" || (inc.type ?? "").startsWith("humain_");
}

// Geste, alerte et choix, lus sur l'incident d'abord, puis dans la chaîne.
function infosGeste(inc: Incident): { geste?: string; avertissement?: string; choix?: ChoixSalarie } {
  const chaine = inc.chaine ?? [];
  const averti = [...chaine].reverse().find((x) => x.phase === "avertissement");
  const action = [...chaine].reverse().find((x) => x.phase === "action_risquee");
  const choixMaillon = [...chaine].reverse().find((x) => x.phase === "choix");
  const evenement = [...(inc.evenements ?? [])].reverse().find((e) => e.type === "avertissement");
  const details = evenement?.details ?? {};
  const texte = (valeur: unknown) => (typeof valeur === "string" && valeur.trim() ? valeur.trim() : undefined);
  const brut = details.choix;
  const choix =
    inc.choix ??
    averti?.choix ??
    (brut === "continuer" || brut === "annuler" ? brut : undefined) ??
    (choixMaillon?.detail.includes("annul")
      ? "annuler"
      : choixMaillon?.detail.includes("continu") || choixMaillon?.detail.includes("passé outre")
        ? "continuer"
        : undefined);
  const nettoyer = (t?: string) => (t ? sansCodes(decoder(t)).replace(/^\[leurre, neutralisé\]\s*/i, "") : undefined);
  return {
    geste: nettoyer(inc.geste ?? action?.detail),
    avertissement: nettoyer(inc.avertissement ?? texte(details.message) ?? averti?.detail),
    choix,
  };
}

function IncidentSalarie({
  incident,
  decisionEnCours,
  erreurDecision,
  trancher,
}: {
  incident: Incident;
  decisionEnCours: DecisionAction | null;
  erreurDecision: string | null;
  trancher: (a: DecisionAction) => void;
}) {
  const { synthese, prete } = useSynthese(incident);
  const { geste, avertissement, choix } = infosGeste(incident);
  const etat = etatIncident(incident);
  const ferme = incident.statut === "clos" || incident.statut === "ignore";
  const chaine = [...(incident.chaine ?? [])].sort(
    (a, b) => (a.horodatage ?? "").localeCompare(b.horodatage ?? "") || a.ordre - b.ordre
  );

  return (
    <div className="ag-dossier">
      <section className="ag-coque ag-entete" aria-labelledby="sal-titre">
        <div className="ag-noyau">
          <div className="ag-entete-haut">
            <span className={`gravite ${incident.gravite}`}>{GRAVITE[incident.gravite] ?? incident.gravite}</span>
            <span className={`inc-etat e-${etat.cls}`}>{etat.lib}</span>
            <span className="ag-meta">
              {libelleType(incident.type)} · signalé à {heure(incident.ouvert_le).slice(0, 5)}
            </span>
          </div>
          <h2 id="sal-titre" className="ag-titre">{titreIncident(incident)}</h2>
          <SyntheseBloc synthese={synthese} prete={prete} repli={[phraseSalarie(incident.type, choix)]} />
        </div>
      </section>

      <div className="ag-grille">
        <section className="ag-coque ag-zone-chaine" aria-labelledby="sal-chaine-titre">
          <div className="ag-noyau">
            <header className="ag-carte-tete">
              <div>
                <span className="ag-sourcil">Sur le poste</span>
                <h3 id="sal-chaine-titre">Ce que le salarié a vu et fait</h3>
              </div>
              <BadgeChoixSalarie choix={choix} />
            </header>
            {geste && (
              <div className="geste-bloc">
                <div className="geste-lib">Le geste</div>
                <div className="geste-val">{geste}</div>
              </div>
            )}
            {avertissement && (
              <div className="geste-bloc">
                <div className="geste-lib">Le message affiché par Dédale</div>
                <div className="geste-popup">{avertissement}</div>
              </div>
            )}
            {chaine.length > 0 && <FriseSalarie chaine={chaine} incident={incident} />}
          </div>
        </section>

        <section className="ag-coque ag-zone-decision issue-salarie" aria-labelledby="sal-decision-titre">
          <div className="ag-noyau">
            <header className="ag-carte-tete">
              <div>
                <span className="ag-sourcil">Votre décision</span>
                <h3 id="sal-decision-titre" className="ag-etat-long">
                  <span className="ag-etat-point" />
                  {ferme ? (incident.statut === "ignore" ? "Classé sans suite" : "Dossier fermé") : "Le dossier attend"}
                </h3>
              </div>
            </header>
            <p className="ag-enjeu">Dédale ne bloque jamais le poste : il prévient le salarié, puis vous décidez de la suite.</p>
            <div className="ag-actions" aria-busy={decisionEnCours !== null}>
              {ACTIONS_HUMAIN.map((a) => (
                <div className="ag-action" key={a.action}>
                  <button
                    type="button"
                    className={`ag-pilule ${a.cls === "primaire" ? "ag-pilule-clore" : "ag-pilule-reprendre"}`}
                    disabled={decisionEnCours !== null || ferme}
                    onClick={() => trancher(a.action)}
                  >
                    <span>{decisionEnCours === a.action ? "Envoi…" : a.lib}</span>
                  </button>
                  <p className="ag-aide">{a.aide}</p>
                </div>
              ))}
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
                    <span className="ag-heure">{heure(d.horodatage)}</span>
                    <span>
                      {d.analyste} {d.action === "ignorer" ? "a classé sans suite" : "a clos le dossier"}
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

// Pourquoi Dédale a réagi et ce que le geste aurait provoqué, par type.
const POURQUOI_GESTE: Record<string, string> = {
  humain_secret: "Dédale a reconnu une clé secrète dans ce que le salarié allait coller.",
  humain_mail_externe: "Le destinataire est hors de l'entreprise et la pièce jointe ressemble à des données clients.",
  humain_upload_ia: "Ce service d'IA n'est pas autorisé par Orbis Pay et le fichier contient des données internes.",
  humain_phishing: "Le lien mène à un site qui imite Orbis Pay sans en faire partie.",
};
const RISQUE_GESTE: Record<string, string> = {
  humain_secret: "La clé aurait été exposée à un service extérieur, sans retour possible.",
  humain_mail_externe: "Les données clients seraient sorties de l'entreprise.",
  humain_upload_ia: "Le fichier serait stocké chez un service que l'entreprise ne contrôle pas.",
  humain_phishing: "Le mot de passe du salarié aurait été volé.",
};

function detailSalarie(m: MaillonChaine, inc: Incident): DetailMaillon {
  const type = inc.type ?? "";
  const texte = sansCodes(decoder(m.detail ?? "")).replace(/^\[leurre, neutralisé\]\s*/i, "");
  const refs = fusionnerRefs(
    (m.risques ?? []).map((r) => lireRef(r.id)),
    (m.techniques ?? []).map((t) => {
      const r = lireRef(t.id, t.cadre);
      return r ? { ...r, nom: t.nom } : null;
    })
  );
  const base = { brut: texte ? [{ lib: "Observé sur le poste", valeur: preuveInerte(texte, 600) }] : [], refs };
  switch (m.phase) {
    case "action_risquee":
      return { ...base, pourquoi: POURQUOI_GESTE[type], risque: RISQUE_GESTE[type] };
    case "avertissement":
      return {
        ...base,
        brut: [
          ...base.brut,
          ...(m.choix ? [{ lib: "Choix du salarié", valeur: m.choix === "annuler" ? "il a annulé" : "il a continué" }] : []),
        ],
        pourquoi: POURQUOI_GESTE[type] ?? "Dédale prévient au moment du geste, avant qu'il n'aboutisse.",
        risque: "Sans cette alerte, le salarié n'aurait rien vu passer.",
      };
    case "choix":
      return { ...base, pourquoi: "Dédale ne bloque pas le poste : le salarié reste libre de choisir." };
    case "consequence":
    case "sortie":
      return {
        ...base,
        pourquoi: "Le salarié a continué malgré l'alerte : le dossier remonte au SOC.",
        risque: RISQUE_GESTE[type],
      };
    default:
      return { ...base, pourquoi: "Dédale observe le poste sans rien bloquer." };
  }
}

function FriseSalarie({ chaine, incident }: { chaine: MaillonChaine[]; incident: Incident }) {
  const [ouverts, setOuverts] = useState<Set<number>>(() => new Set());
  const basculer = (i: number) =>
    setOuverts((s) => {
      const c = new Set(s);
      if (c.has(i)) c.delete(i);
      else c.add(i);
      return c;
    });
  return (
    <div className="frise">
      {chaine.map((m, i) => {
        const ouvert = ouverts.has(i);
        const id = `sal-etape-${i}`;
        return (
          <div key={`${m.ordre}-${i}`} className={`maillon phase-${m.phase} ${ouvert ? "deplie" : ""}`}>
            <span className="puce" />
            <button type="button" className="sal-etape-btn" aria-expanded={ouvert} aria-controls={id} onClick={() => basculer(i)}>
              <span className="m-titre">
                <span className="m-phase">{PHASE_LIB[m.phase] ?? "Étape"}</span>
                <strong>{sansCodes(decoder(m.titre))}</strong>
                <span className="m-heure">{heure(m.horodatage)}</span>
                <span className="ag-chevron" aria-hidden="true" />
              </span>
              <span className="m-detail">{sansCodes(decoder(m.detail)).replace(/^\[leurre, neutralisé\]\s*/i, "")}</span>
            </button>
            <Depliant ouvert={ouvert} id={id}>
              <DetailEtape detail={detailSalarie(m, incident)} horodatage={m.horodatage} />
            </Depliant>
          </div>
        );
      })}
    </div>
  );
}
