import type {
  Activite,
  DocumentSource,
  Incident,
  Leurre,
  Mesures,
  MessageWS,
  RetraitDroit,
  Session,
  DecisionAction,
  Evenement,
  Synthese,
  TempsSession,
} from "../types";

// Interface unique que la console consomme. Deux implémentations : le backend
// réel (sourceLive) et le mock local (sourceMock, voir mock.ts). L'UI ne sait
// pas laquelle elle utilise.
export interface SourceDonnees {
  readonly nom: "live" | "mock";
  getSessions(): Promise<Session[]>;
  getIncidents(): Promise<Incident[]>;
  getIncident(id: string): Promise<Incident>;
  getLeurres(): Promise<Leurre[]>;
  getMesures(): Promise<Mesures>;
  postDecision(
    id: string,
    action: DecisionAction,
    analyste: string
  ): Promise<Incident>;
  // Copilote SOC : résumé en phrases, confiance, décision conseillée.
  getSynthese(id: string): Promise<Synthese>;
  // Contenu lu par l'agent (mail, document), désarmé, partie piégée repérée.
  getSource(id: string): Promise<DocumentSource[]>;
  // Fil des agents : dernières actions passées par la passerelle.
  getActivite(limite: number): Promise<Activite[]>;
  // Correctif en un clic : retire un droit en trop à l'agent.
  retirerDroit(id: string, droit: string, analyste: string): Promise<RetraitDroit>;
  // S'abonne au flux ; renvoie une fonction de désabonnement.
  connecter(
    onMessage: (m: MessageWS) => void,
    onEtat: (etat: "connecte" | "reconnexion" | "absent") => void
  ): () => void;
}

const BASE = ""; // relatif : proxy en dev, même origine en prod

async function j<T>(chemin: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(BASE + chemin, { signal });
  if (!r.ok) throw new Error(`${chemin} → ${r.status}`);
  return (await r.json()) as T;
}

// Le backend emballe ses listes : {sessions:[…]}, {incidents:[…]}, {leurres:[…]}.
// On accepte aussi un tableau brut, au cas où le contrat évoluerait.
async function liste<T>(chemin: string, cle: string, signal?: AbortSignal): Promise<T[]> {
  const data = await j<unknown>(chemin, signal);
  if (Array.isArray(data)) return data as T[];
  if (data && typeof data === "object") {
    const v = (data as Record<string, unknown>)[cle];
    if (Array.isArray(v)) return v as T[];
  }
  return [];
}

export const sourceLive: SourceDonnees = {
  nom: "live",
  getSessions: () => liste<Session>("/api/sessions", "sessions"),
  getIncidents: () => liste<Incident>("/api/incidents", "incidents"),
  getIncident: async (id) => {
    const incident = await j<Incident>(`/api/incidents/${encodeURIComponent(id)}`);
    // Salarié et agent interne : le journal de session porte le geste, ou les
    // appels d'outils et canaris dont la boîte noire de l'agent a besoin.
    if (incident.source === "humain" || incident.source === "physique" || incident.source === "interne") {
      try {
        const session = await j<{ evenements: Evenement[] } & TempsSession>(
          `/api/sessions/${encodeURIComponent(incident.session_id)}`
        );
        return {
          ...incident,
          evenements: session.evenements,
          temps_session: {
            premiere_vue: session.premiere_vue,
            derniere_vue: session.derniere_vue,
            detecte_a: session.detecte_a,
            confine_a: session.confine_a,
          },
        };
      } catch {
        // Le détail de l'incident reste consultable si le journal de session échoue.
      }
    }
    return incident;
  },
  getLeurres: () => liste<Leurre>("/api/leurres", "leurres"),
  getMesures: () => j<Mesures>("/api/mesures"),
  postDecision: async (id, action, analyste) => {
    const ctrl = new AbortController();
    const minuteur = setTimeout(() => ctrl.abort(), 10000);
    try {
      const r = await fetch(
        BASE + `/api/incidents/${encodeURIComponent(id)}/decision`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ action, analyste }),
          signal: ctrl.signal,
        }
      );
      if (!r.ok) throw new Error(`Décision refusée par le backend (HTTP ${r.status}).`);
      return (await r.json()) as Incident;
    } catch (erreur) {
      if (ctrl.signal.aborted || erreur instanceof TypeError) {
        throw new Error("Réponse du backend non reçue. Vérifiez le journal avant de réessayer : la décision a peut-être été enregistrée.");
      }
      throw erreur;
    } finally {
      clearTimeout(minuteur);
    }
  },

  getSynthese: (id) => j<Synthese>(`/api/incidents/${encodeURIComponent(id)}/synthese`),
  getSource: (id) => liste<DocumentSource>(`/api/incidents/${encodeURIComponent(id)}/source`, "documents"),
  getActivite: (limite) => liste<Activite>(`/api/activite?limite=${limite}`, "activite"),
  retirerDroit: async (id, droit, analyste) => {
    const r = await fetch(BASE + `/api/incidents/${encodeURIComponent(id)}/retirer-droit`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ droit, analyste }),
    });
    if (!r.ok) {
      // 400 : le droit n'est pas retirable (déjà retiré, nécessaire à la tâche…).
      let detail = "";
      try {
        const corps = (await r.json()) as { detail?: unknown };
        detail = typeof corps.detail === "string" ? corps.detail : "";
      } catch {
        /* corps non JSON */
      }
      throw new Error(detail ? `Retrait refusé : ${detail}` : `Retrait refusé par le backend (HTTP ${r.status}).`);
    }
    return (await r.json()) as RetraitDroit;
  },

  connecter(onMessage, onEtat) {
    let ws: WebSocket | null = null;
    let fermé = false;
    let delai = 1000;
    let minuteur: ReturnType<typeof setTimeout> | null = null;

    const url = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      return `${proto}://${location.host}/ws`;
    };

    const ouvrir = () => {
      if (fermé) return;
      onEtat("reconnexion");
      try {
        ws = new WebSocket(url());
      } catch {
        planifier();
        return;
      }
      ws.onopen = () => {
        delai = 1000;
        onEtat("connecte");
      };
      ws.onmessage = (ev) => {
        try {
          onMessage(JSON.parse(ev.data) as MessageWS);
        } catch {
          /* message non-JSON ignoré */
        }
      };
      ws.onclose = () => {
        if (!fermé) planifier();
      };
      ws.onerror = () => {
        try {
          ws?.close();
        } catch {
          /* ignore */
        }
      };
    };

    const planifier = () => {
      onEtat("absent");
      if (minuteur) clearTimeout(minuteur);
      minuteur = setTimeout(ouvrir, delai);
      delai = Math.min(delai * 2, 10000);
    };

    ouvrir();

    return () => {
      fermé = true;
      if (minuteur) clearTimeout(minuteur);
      try {
        ws?.close();
      } catch {
        /* ignore */
      }
    };
  },
};

// Teste la présence du backend (timeout court). Vrai = backend joignable.
export async function backendJoignable(timeoutMs = 1500): Promise<boolean> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    await j<unknown>("/api/mesures", ctrl.signal);
    return true;
  } catch {
    return false;
  } finally {
    clearTimeout(t);
  }
}
