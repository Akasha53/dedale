import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type {
  ActionRemediation,
  Activite,
  AgentInventaire,
  AnalysePolitique,
  DecisionAction,
  DocumentSource,
  EtatFlux,
  Incident,
  Leurre,
  Mesures,
  MessageWS,
  ModeConnexion,
  Politique,
  Remediation,
  RetraitDroit,
  RevelationIdentite,
  Verification,
  Session,
  Synthese,
} from "../types";
import { backendJoignable, sourceLive, type SourceDonnees } from "./source";
import { visibleConsole } from "../ui/primitives";
import { definirAgents } from "../ui/mots";
import { creerSourceMock } from "./mock";

interface Etat {
  mode: ModeConnexion;
  flux: EtatFlux;
  sessions: Session[];
  incidents: Incident[];
  leurres: Leurre[];
  mesures: Mesures | null;
  activite: Activite[];
  inventaire: AgentInventaire[];
  politiques: Politique[];
  chargement: boolean;
  erreur: string | null;
  rafraichir: () => Promise<void>;
  getIncident: (id: string) => Promise<Incident>;
  decider: (id: string, action: DecisionAction, analyste: string, motif?: string) => Promise<Incident>;
  analyserPolitique: (phrase: string) => Promise<AnalysePolitique>;
  activerPolitique: (phrase: string, regle: Record<string, unknown> | null, analyste: string) => Promise<Politique>;
  retirerPolitique: (id: string, analyste: string) => Promise<void>;
  getVerification: (id: string) => Promise<Verification>;
  revelerIdentite: (id: string, motif: string, analyste: string) => Promise<RevelationIdentite>;
  remedier: (id: string, action: ActionRemediation, analyste: string) => Promise<Remediation>;
  getSynthese: (id: string) => Promise<Synthese>;
  getSource: (id: string) => Promise<DocumentSource[]>;
  retirerDroit: (id: string, droit: string, analyste: string) => Promise<RetraitDroit>;
}

// Taille du fil des agents gardée en mémoire.
const TAILLE_FIL = 60;

function fusionnerActivite(nouvelles: Activite[], anciennes: Activite[]): Activite[] {
  const vus = new Set<string>();
  const sortie: Activite[] = [];
  for (const a of [...nouvelles, ...anciennes]) {
    const cle = String(a.id);
    if (vus.has(cle)) continue;
    vus.add(cle);
    sortie.push(a);
  }
  return sortie
    .sort((a, b) => (b.heure ?? "").localeCompare(a.heure ?? ""))
    .slice(0, TAILLE_FIL);
}

const Ctx = createContext<Etat | null>(null);

export function DataProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<ModeConnexion>("connexion");
  const [flux, setFlux] = useState<EtatFlux>("absent");
  const [sessions, setSessions] = useState<Session[]>([]);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [leurres, setLeurres] = useState<Leurre[]>([]);
  const [mesures, setMesures] = useState<Mesures | null>(null);
  const [activite, setActivite] = useState<Activite[]>([]);
  const [inventaire, setInventaire] = useState<AgentInventaire[]>([]);
  const [politiques, setPolitiques] = useState<Politique[]>([]);
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState<string | null>(null);

  const sourceRef = useRef<SourceDonnees | null>(null);
  const deconnecterRef = useRef<(() => void) | null>(null);

  const chargerTout = useCallback(async (src: SourceDonnees) => {
    const [se, inc, le, me, ac, inv, pol] = await Promise.allSettled([
      src.getSessions(), src.getIncidents(), src.getLeurres(), src.getMesures(), src.getActivite(TAILLE_FIL),
      src.getInventaire(), src.getPolitiques(),
    ]);
    if (sourceRef.current !== src) return;
    // Deux piliers seulement, agents IA et salariés : la surface externe et le
    // volet physique ne s'affichent pas et n'entrent dans aucun total.
    if (se.status === "fulfilled") setSessions(se.value.filter(visibleConsole));
    if (inc.status === "fulfilled") setIncidents(inc.value.filter(visibleConsole));
    if (le.status === "fulfilled") setLeurres(le.value);
    if (me.status === "fulfilled") setMesures(me.value);
    // Le fil des agents est un plus : une route absente ne compte pas comme
    // une actualisation incomplète.
    if (ac.status === "fulfilled") setActivite((prev) => fusionnerActivite(ac.value, prev));
    // Inventaire et règles : routes récentes, leur absence ne bloque rien.
    if (inv.status === "fulfilled") {
      definirAgents(inv.value);
      setInventaire(inv.value);
    }
    if (pol.status === "fulfilled") setPolitiques(pol.value);
    setErreur([se, inc, le, me].some((r) => r.status === "rejected")
      ? "Actualisation incomplète. Les dernières données reçues restent affichées."
      : null);
  }, []);

  const rafraichir = useCallback(async () => {
    const src = sourceRef.current;
    if (!src) return;
    try {
      await chargerTout(src);
    } catch (e) {
      setErreur(e instanceof Error ? e.message : "erreur de chargement");
    }
  }, [chargerTout]);

  const onMessage = useCallback((m: MessageWS) => {
    if (m.type === "session") {
      const s = m.donnees as Session;
      if (!s?.id || !visibleConsole(s)) return;
      setSessions((prev) => {
        const i = prev.findIndex((x) => x.id === s.id);
        if (i === -1) return [{ ...s }, ...prev];
        const copie = prev.slice();
        copie[i] = { ...copie[i], ...s };
        return copie;
      });
    } else if (m.type === "incident") {
      const inc = m.donnees as Incident;
      if (!inc?.id || !visibleConsole(inc)) return;
      setIncidents((prev) => {
        const i = prev.findIndex((x) => x.id === inc.id);
        if (i === -1) return [{ ...inc }, ...prev];
        const copie = prev.slice();
        copie[i] = { ...copie[i], ...inc };
        return copie;
      });
    } else if (m.type === "activite") {
      const a = m.donnees as Activite;
      if (a?.id == null) return;
      setActivite((prev) => fusionnerActivite([a], prev));
    }
    // Les événements bruts alimentent surtout le flux ; la vue temps réel se
    // rafraîchit via les messages "session"/"incident".
  }, []);

  const brancher = useCallback(
    (src: SourceDonnees) => {
      deconnecterRef.current?.();
      deconnecterRef.current = src.connecter(onMessage, setFlux);
    },
    [onMessage]
  );

  // Démarrage : sonder le backend, choisir la source, charger, brancher le flux.
  useEffect(() => {
    let vivant = true;
    (async () => {
      setChargement(true);
      const dispo = await backendJoignable();
      if (!vivant) return;
      const src = dispo ? sourceLive : creerSourceMock();
      sourceRef.current = src;
      setActivite([]);
      setMode(src.nom);
      await chargerTout(src);
      brancher(src);
      setChargement(false);
    })();
    return () => {
      vivant = false;
      deconnecterRef.current?.();
    };
  }, [chargerTout, brancher]);

  // Tant qu'on est sur le mock, re-sonder le backend et basculer dès qu'il répond.
  useEffect(() => {
    if (mode !== "mock") return;
    const t = setInterval(async () => {
      if (await backendJoignable()) {
        const src = sourceLive;
        sourceRef.current = src;
        setActivite([]);
        setMode("live");
        await chargerTout(src);
        brancher(src);
      }
    }, 5000);
    return () => clearInterval(t);
  }, [mode, chargerTout, brancher]);

  // En live, rafraîchir périodiquement les listes (filet si le WS est muet).
  useEffect(() => {
    if (mode !== "live") return;
    const t = setInterval(() => void rafraichir(), 8000);
    return () => clearInterval(t);
  }, [mode, rafraichir]);

  const decider = useCallback(
    async (id: string, action: DecisionAction, analyste: string, motif?: string) => {
      const src = sourceRef.current;
      if (!src) throw new Error("Connexion au backend en cours. Réessayez après le chargement.");
      const incident = await src.postDecision(id, action, analyste, motif);
      setIncidents((prev) => prev.map((i) => i.id === id ? { ...i, ...incident } : i));
      setSessions((prev) => prev.map((s) => s.id === incident.session_id ? { ...s, etat: incident.etat } : s));
      void rafraichir();
      return incident;
    },
    [rafraichir]
  );

  const getIncident = useCallback(
    (id: string) => sourceRef.current!.getIncident(id),
    []
  );

  const getSynthese = useCallback((id: string) => {
    const src = sourceRef.current;
    if (!src) return Promise.reject(new Error("source absente"));
    return src.getSynthese(id);
  }, []);

  const getSource = useCallback((id: string) => {
    const src = sourceRef.current;
    if (!src) return Promise.reject(new Error("source absente"));
    return src.getSource(id);
  }, []);

  const retirerDroit = useCallback(
    async (id: string, droit: string, analyste: string) => {
      const src = sourceRef.current;
      if (!src) throw new Error("Connexion au backend en cours. Réessayez après le chargement.");
      const res = await src.retirerDroit(id, droit, analyste);
      if (res.incident) {
        const maj = res.incident;
        setIncidents((prev) => prev.map((i) => (i.id === id ? { ...i, ...maj } : i)));
      }
      void rafraichir();
      return res;
    },
    [rafraichir]
  );

  const source = () => {
    const src = sourceRef.current;
    if (!src) throw new Error("Connexion au backend en cours. Réessayez après le chargement.");
    return src;
  };

  const analyserPolitique = useCallback((phrase: string) => source().analyserPolitique(phrase), []);
  const activerPolitique = useCallback(
    async (phrase: string, regle: Record<string, unknown> | null, analyste: string) => {
      const p = await source().activerPolitique(phrase, regle, analyste);
      void rafraichir();
      return p;
    },
    [rafraichir]
  );
  const retirerPolitique = useCallback(
    async (id: string, analyste: string) => {
      await source().retirerPolitique(id, analyste);
      setPolitiques((prev) => prev.filter((p) => p.id !== id));
      void rafraichir();
    },
    [rafraichir]
  );
  const getVerification = useCallback((id: string) => source().getVerification(id), []);
  const revelerIdentite = useCallback(
    async (id: string, motif: string, analyste: string) => {
      const r = await source().revelerIdentite(id, motif, analyste);
      void rafraichir();
      return r;
    },
    [rafraichir]
  );
  const remedier = useCallback(
    async (id: string, action: ActionRemediation, analyste: string) => {
      const r = await source().remedier(id, action, analyste);
      void rafraichir();
      return r;
    },
    [rafraichir]
  );

  const valeur: Etat = {
    mode,
    flux,
    sessions,
    incidents,
    leurres,
    mesures,
    activite,
    inventaire,
    politiques,
    chargement,
    erreur,
    rafraichir,
    getIncident,
    decider,
    getSynthese,
    getSource,
    retirerDroit,
    analyserPolitique,
    activerPolitique,
    retirerPolitique,
    getVerification,
    revelerIdentite,
    remedier,
  };

  return <Ctx.Provider value={valeur}>{children}</Ctx.Provider>;
}

export function useDonnees(): Etat {
  const v = useContext(Ctx);
  if (!v) throw new Error("useDonnees hors DataProvider");
  return v;
}
