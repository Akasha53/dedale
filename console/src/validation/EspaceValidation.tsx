import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import logoDedale from "../assets/dedale.svg";
import {
  chargerFile,
  contrepartie,
  decider,
  entier,
  ErreurApi,
  euros,
  heure,
  jourEtHeure,
  personne,
  resume,
  type FicheGeste,
  type FileValidation,
  type Qualite,
} from "./api";

// Espace du responsable du salarié et de la finance : une liste, une fiche,
// deux boutons. Aucune donnée de sécurité ici : ni score, ni lien, ni agent.

const RELEVE_MS = 3000;
const CLE_SIGNATURE = "dedale.validation.signature";

type Connexion = "chargement" | "ok" | "hors_ligne" | "refuse";

interface Signature {
  nom: string;
  qualite: Qualite;
}

function lireSignature(): Signature {
  try {
    const brut = window.localStorage.getItem(CLE_SIGNATURE);
    if (brut) {
      const s = JSON.parse(brut) as Partial<Signature>;
      return { nom: typeof s.nom === "string" ? s.nom : "", qualite: s.qualite === "finance" ? "finance" : "responsable" };
    }
  } catch {
    // stockage indisponible : on redemande
  }
  return { nom: "", qualite: "responsable" };
}

function garderSignature(s: Signature) {
  try {
    window.localStorage.setItem(CLE_SIGNATURE, JSON.stringify(s));
  } catch {
    // stockage indisponible : la signature vaut pour cette page
  }
}

export function EspaceValidation() {
  const [file, setFile] = useState<FileValidation | null>(null);
  const [connexion, setConnexion] = useState<Connexion>("chargement");
  // `?geste=<id>` ouvre directement une fiche (lien envoyé au responsable).
  const [choix, setChoix] = useState<string | null>(() => new URLSearchParams(window.location.search).get("geste"));
  const ficheRef = useRef<HTMLElement | null>(null);

  const relever = useCallback(async (signal?: AbortSignal) => {
    try {
      const f = await chargerFile(signal);
      setFile(f);
      setConnexion("ok");
    } catch (e) {
      if (signal?.aborted) return;
      setConnexion(e instanceof ErreurApi && (e.statut === 401 || e.statut === 403) ? "refuse" : "hors_ligne");
    }
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    void relever(ctrl.signal);
    const t = window.setInterval(() => void relever(), RELEVE_MS);
    return () => {
      ctrl.abort();
      window.clearInterval(t);
    };
  }, [relever]);

  const toutes = useMemo(() => [...(file?.gestes ?? []), ...(file?.traites ?? [])], [file]);
  // Sans choix, la fiche ouverte est le plus récent geste à confirmer.
  const courante = toutes.find((f) => f.id === choix) ?? file?.gestes[0] ?? null;

  const ouvrir = (id: string) => {
    setChoix(id);
    if (window.matchMedia("(max-width: 900px)").matches) {
      window.requestAnimationFrame(() => ficheRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
    }
  };

  const apresDecision = (f: FicheGeste) => {
    setFile((prec) =>
      prec
        ? {
            gestes: prec.gestes.filter((g) => g.id !== f.id),
            traites: [f, ...prec.traites.filter((g) => g.id !== f.id)],
            total: Math.max(0, prec.total - 1),
          }
        : prec
    );
    setChoix(f.id);
  };

  return (
    <div className="val">
      <header className="val-entete">
        <a className="val-marque" href="./" aria-label="Dédale, validation métier">
          <img src={logoDedale} width={28} height={28} alt="" />
          <span>
            <span className="val-nom">Dédale</span>
            <span className="val-sous">Validation métier · Orbis Pay</span>
          </span>
        </a>
        <EtatConnexion connexion={connexion} />
      </header>

      <main className="val-corps">
        <section className="val-intro val-apparait">
          <span className="val-sourcil">Responsable et finance</span>
          <h1>Gestes à confirmer</h1>
          <p>
            Dédale a retenu ces gestes parce qu'un détail sort de l'habitude : bénéficiaire nouveau, RIB qui
            change, montant élevé. Confirmez ou refusez, avec un motif. L'équipe sécurité ne voit ni les
            montants ni les bénéficiaires.
          </p>
        </section>

        {connexion === "refuse" ? (
          <Message titre="Accès réservé">
            Cet espace s'ouvre avec l'accès d'un responsable ou de la finance. La console de l'équipe
            sécurité n'y donne pas accès.
          </Message>
        ) : !file ? (
          connexion === "hors_ligne" ? (
            <Message titre="Le serveur ne répond pas">Nouvel essai dans quelques secondes.</Message>
          ) : (
            <div className="val-attente" aria-live="polite">Chargement…</div>
          )
        ) : (
          <div className="val-grille">
            <Liste file={file} courante={courante?.id ?? null} ouvrir={ouvrir} />
            <section ref={ficheRef} className="val-zone-fiche" aria-label="Fiche du geste">
              {courante ? (
                <Fiche key={courante.id} fiche={courante} apresDecision={apresDecision} />
              ) : (
                <Message titre="Rien à confirmer">
                  Un geste retenu par Dédale apparaît ici quelques secondes après la demande du salarié.
                </Message>
              )}
            </section>
          </div>
        )}
      </main>
    </div>
  );
}

function EtatConnexion({ connexion }: { connexion: Connexion }) {
  const lib = { chargement: "Connexion…", ok: "À jour", hors_ligne: "Hors ligne", refuse: "Accès refusé" }[connexion];
  return (
    <span className={`val-connexion c-${connexion}`} role="status">
      <span className="val-point" aria-hidden="true" />
      {lib}
    </span>
  );
}

function Message({ titre, children }: { titre: string; children: ReactNode }) {
  return (
    <div className="val-message val-apparait">
      <p className="val-message-titre">{titre}</p>
      <p>{children}</p>
    </div>
  );
}

// ---------- liste ----------

function Liste({ file, courante, ouvrir }: { file: FileValidation; courante: string | null; ouvrir: (id: string) => void }) {
  return (
    <nav className="val-liste val-apparait" aria-label="Gestes">
      <h2 className="val-liste-titre">
        À confirmer <span className="val-compte">{file.gestes.length}</span>
      </h2>
      {file.gestes.length === 0 ? (
        <p className="val-liste-vide">Rien en attente.</p>
      ) : (
        <ul>
          {file.gestes.map((f, i) => (
            <Ligne key={f.id} fiche={f} active={f.id === courante} ouvrir={ouvrir} rang={i} />
          ))}
        </ul>
      )}
      {file.traites.length > 0 && (
        <>
          <h2 className="val-liste-titre val-liste-titre-2">Déjà tranchés</h2>
          <ul>
            {file.traites.map((f, i) => (
              <Ligne key={f.id} fiche={f} active={f.id === courante} ouvrir={ouvrir} rang={i} />
            ))}
          </ul>
        </>
      )}
    </nav>
  );
}

function Ligne({ fiche, active, ouvrir, rang }: { fiche: FicheGeste; active: boolean; ouvrir: (id: string) => void; rang: number }) {
  const ton = fiche.statut === "en_attente" ? "attente" : fiche.statut === "accorde" ? "regle" : "refuse";
  const quand = fiche.statut === "en_attente" ? heure(fiche.demande_le) : heure(fiche.decision?.horodatage);
  return (
    <li style={{ ["--rang" as string]: rang }}>
      <button
        type="button"
        className={`val-ligne ${active ? "active" : ""}`}
        aria-current={active ? "true" : undefined}
        onClick={() => ouvrir(fiche.id)}
      >
        <span className={`val-point t-${ton}`} aria-hidden="true" />
        <span className="val-ligne-texte">
          <span className="val-ligne-titre">{resume(fiche)}</span>
          <span className="val-ligne-sous">
            {contrepartie(fiche)} · {fiche.demandeur?.nom ?? "poste hors annuaire"}
          </span>
        </span>
        <span className="val-ligne-heure">
          {fiche.statut === "accorde" ? "Accordé" : fiche.statut === "refuse" ? "Refusé" : quand}
        </span>
      </button>
    </li>
  );
}

// ---------- fiche ----------

function Fiche({ fiche, apresDecision }: { fiche: FicheGeste; apresDecision: (f: FicheGeste) => void }) {
  const b = fiche.beneficiaire;
  const enAttente = fiche.statut === "en_attente";
  return (
    <article className="val-coque val-apparait" aria-labelledby="val-fiche-titre">
      <div className="val-noyau">
        <div className="val-fiche-haut">
          <span className={`val-pastille t-${enAttente ? "attente" : fiche.statut === "accorde" ? "regle" : "refuse"}`}>
            {enAttente ? "À confirmer" : fiche.statut === "accorde" ? "Accordé" : "Refusé"}
          </span>
          <span className="val-fiche-quand">Demandé {jourEtHeure(fiche.demande_le)}</span>
        </div>

        <p className="val-geste" id="val-fiche-titre">{fiche.titre}</p>
        {fiche.geste === "virement" ? (
          <>
            <p className="val-montant">{euros(fiche.montant_eur)}</p>
            <p className="val-vers">à {b?.nom ?? "un bénéficiaire non lu"}</p>
          </>
        ) : fiche.geste === "export_clients" ? (
          <>
            <p className="val-montant">{entier(fiche.volume)} fiches</p>
            <p className="val-vers">vers {fiche.destination ?? "une destination non lue"}</p>
          </>
        ) : null}

        {fiche.raisons.length > 0 || fiche.motif ? (
          <div className="val-pourquoi">
            <h3>Pourquoi Dédale l'a retenu</h3>
            {fiche.raisons.length > 0 ? (
              <ul>
                {fiche.raisons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            ) : (
              <p>{fiche.motif}</p>
            )}
          </div>
        ) : null}

        <dl className="val-details">
          {fiche.geste === "virement" && (
            <>
              <Ligned terme="Bénéficiaire">
                {b?.nom ?? "non lu"}
                <span className="val-precision">
                  {b?.connu
                    ? [b.nature === "client" ? "client" : "fournisseur habituel", b.objet].filter(Boolean).join(" · ")
                    : "jamais payé par l'entreprise"}
                </span>
              </Ligned>
              <Ligned terme="IBAN">
                <span className="val-chiffres">{fiche.iban ?? "non indiqué"}</span>
                {fiche.rib === "nouveau" && <span className="val-precision t-attente">Nouveau pour ce bénéficiaire</span>}
                {fiche.rib === "habituel" && <span className="val-precision">Celui déjà enregistré</span>}
              </Ligned>
              {typeof b?.montant_habituel_eur === "number" && (
                <Ligned terme="Montant habituel">
                  <span className="val-chiffres">{euros(b.montant_habituel_eur, true)}</span>
                </Ligned>
              )}
            </>
          )}
          <Ligned terme="Demandé par">{personne(fiche)}</Ligned>
          {fiche.demande && (
            <Ligned terme="Sa demande">
              <span className="val-citation">{fiche.demande}</span>
            </Ligned>
          )}
        </dl>

        {enAttente ? <Decision fiche={fiche} apresDecision={apresDecision} /> : <Tranche fiche={fiche} />}
      </div>
    </article>
  );
}

function Ligned({ terme, children }: { terme: string; children: ReactNode }) {
  return (
    <div className="val-detail">
      <dt>{terme}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function Tranche({ fiche }: { fiche: FicheGeste }) {
  const d = fiche.decision;
  const accorde = fiche.statut === "accorde";
  return (
    <div className={`val-tranche t-${accorde ? "regle" : "refuse"}`}>
      <p className="val-tranche-titre">
        {accorde ? "Accordé" : "Refusé"}
        {d?.validateur ? ` par ${d.validateur}` : ""}
        {d?.horodatage ? ` ${jourEtHeure(d.horodatage)}` : ""}
      </p>
      {d?.motif && <p className="val-citation">{d.motif}</p>}
      <p className="val-note">
        {accorde
          ? "Le salarié peut relancer son geste : Dédale le laissera passer pour ce bénéficiaire et un montant proche."
          : "Si le salarié relance ce geste, Dédale le retiendra de nouveau."}
      </p>
    </div>
  );
}

function Decision({ fiche, apresDecision }: { fiche: FicheGeste; apresDecision: (f: FicheGeste) => void }) {
  const [signature, setSignature] = useState<Signature>(lireSignature);
  const [motif, setMotif] = useState("");
  const [envoi, setEnvoi] = useState<"accorder" | "refuser" | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);

  const pret = motif.trim().length >= 4 && signature.nom.trim().length >= 2;

  const trancher = async (decision: "accorder" | "refuser", e?: FormEvent) => {
    e?.preventDefault();
    if (envoi) return;
    if (signature.nom.trim().length < 2) {
      setErreur("Indiquez votre nom : il signe la décision.");
      return;
    }
    if (motif.trim().length < 4) {
      setErreur("Un motif est obligatoire : quelques mots suffisent.");
      return;
    }
    setEnvoi(decision);
    setErreur(null);
    garderSignature(signature);
    try {
      apresDecision(await decider(fiche.id, decision, motif.trim(), signature.nom.trim(), signature.qualite));
    } catch (err) {
      setErreur(err instanceof Error ? err.message : "La décision n'est pas partie. Réessayez.");
    } finally {
      setEnvoi(null);
    }
  };

  return (
    <form className="val-decision" onSubmit={(e) => void trancher("accorder", e)}>
      <label className="val-champ">
        <span className="val-etiquette">
          Motif <span>obligatoire</span>
        </span>
        <textarea
          rows={3}
          maxLength={300}
          value={motif}
          onChange={(e) => setMotif(e.target.value)}
          placeholder="Par exemple : RIB confirmé par téléphone avec le fournisseur."
        />
      </label>

      <div className="val-signature">
        <label className="val-champ val-champ-nom">
          <span className="val-etiquette">Signé par</span>
          <input
            type="text"
            value={signature.nom}
            maxLength={60}
            autoComplete="name"
            placeholder="Votre nom"
            onChange={(e) => setSignature({ ...signature, nom: e.target.value })}
          />
        </label>
        <div className="val-segment" role="radiogroup" aria-label="Vous signez en tant que">
          {(["responsable", "finance"] as const).map((q) => (
            <button
              key={q}
              type="button"
              role="radio"
              aria-checked={signature.qualite === q}
              className={signature.qualite === q ? "actif" : ""}
              onClick={() => setSignature({ ...signature, qualite: q })}
            >
              {q === "responsable" ? "Responsable" : "Finance"}
            </button>
          ))}
        </div>
      </div>

      {erreur && (
        <p className="val-erreur" role="alert">
          {erreur}
        </p>
      )}

      <div className="val-boutons">
        <button
          type="button"
          className="val-btn val-btn-refus"
          disabled={envoi !== null}
          onClick={() => void trancher("refuser")}
        >
          {envoi === "refuser" ? "Envoi…" : "Refuser"}
        </button>
        <button type="submit" className="val-btn val-btn-accord" disabled={envoi !== null} aria-disabled={!pret}>
          {envoi === "accorder" ? "Envoi…" : "Accorder"}
          <span className="val-btn-icone" aria-hidden="true">
            <svg viewBox="0 0 16 16" width="14" height="14">
              <path d="M3.5 8.5l3 3 6-7" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
        </button>
      </div>
      <p className="val-note">
        Votre nom et votre motif sont notés au journal scellé. L'équipe sécurité voit seulement que le geste a
        été confirmé ou refusé.
      </p>
    </form>
  );
}
