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
  DecisionAction,
  EtatFlux,
  Incident,
  Leurre,
  Mesures,
  MessageWS,
  ModeConnexion,
  Session,
} from "../types";
import { backendJoignable, sourceLive, type SourceDonnees } from "./source";
import { creerSourceMock } from "./mock";

interface Etat {
  mode: ModeConnexion;
  flux: EtatFlux;
  sessions: Session[];
  incidents: Incident[];
  leurres: Leurre[];
  mesures: Mesures | null;
  chargement: boolean;
  erreur: string | null;
  rafraichir: () => Promise<void>;
  getIncident: (id: string) => Promise<Incident>;
  decider: (id: string, action: DecisionAction, analyste: string) => Promise<Incident>;
  nis2: (id: string) => Promise<string>;
  exporter: (id: string, format: "ecs" | "sigma") => Promise<string>;
}

const Ctx = createContext<Etat | null>(null);

export function DataProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<ModeConnexion>("connexion");
  const [flux, setFlux] = useState<EtatFlux>("absent");
  const [sessions, setSessions] = useState<Session[]>([]);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [leurres, setLeurres] = useState<Leurre[]>([]);
  const [mesures, setMesures] = useState<Mesures | null>(null);
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState<string | null>(null);

  const sourceRef = useRef<SourceDonnees | null>(null);
  const deconnecterRef = useRef<(() => void) | null>(null);

  const chargerTout = useCallback(async (src: SourceDonnees) => {
    const [se, inc, le, me] = await Promise.allSettled([
      src.getSessions(), src.getIncidents(), src.getLeurres(), src.getMesures(),
    ]);
    if (sourceRef.current !== src) return;
    if (se.status === "fulfilled") setSessions(se.value);
    if (inc.status === "fulfilled") setIncidents(inc.value);
    if (le.status === "fulfilled") setLeurres(le.value);
    if (me.status === "fulfilled") setMesures(me.value);
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
      if (!s?.id) return;
      setSessions((prev) => {
        const i = prev.findIndex((x) => x.id === s.id);
        if (i === -1) return [{ ...s }, ...prev];
        const copie = prev.slice();
        copie[i] = { ...copie[i], ...s };
        return copie;
      });
    } else if (m.type === "incident") {
      const inc = m.donnees as Incident;
      if (!inc?.id) return;
      setIncidents((prev) => {
        const i = prev.findIndex((x) => x.id === inc.id);
        if (i === -1) return [{ ...inc }, ...prev];
        const copie = prev.slice();
        copie[i] = { ...copie[i], ...inc };
        return copie;
      });
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
    async (id: string, action: DecisionAction, analyste: string) => {
      const src = sourceRef.current;
      if (!src) throw new Error("Connexion au backend en cours. Réessayez après le chargement.");
      const incident = await src.postDecision(id, action, analyste);
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
  const nis2 = useCallback(
    (id: string) => sourceRef.current!.getNis2(id),
    []
  );
  const exporter = useCallback(
    (id: string, format: "ecs" | "sigma") =>
      sourceRef.current!.getExport(id, format),
    []
  );

  const valeur: Etat = {
    mode,
    flux,
    sessions,
    incidents,
    leurres,
    mesures,
    chargement,
    erreur,
    rafraichir,
    getIncident,
    decider,
    nis2,
    exporter,
  };

  return <Ctx.Provider value={valeur}>{children}</Ctx.Provider>;
}

export function useDonnees(): Etat {
  const v = useContext(Ctx);
  if (!v) throw new Error("useDonnees hors DataProvider");
  return v;
}
