import type {
  Incident,
  Leurre,
  Mesures,
  MessageWS,
  Session,
  DecisionAction,
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
  ): Promise<void>;
  getNis2(id: string): Promise<string>;
  getExport(id: string, format: "ecs" | "sigma"): Promise<string>;
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

async function texte(chemin: string): Promise<string> {
  const r = await fetch(BASE + chemin);
  if (!r.ok) throw new Error(`${chemin} → ${r.status}`);
  const ct = r.headers.get("content-type") || "";
  if (ct.includes("application/json")) {
    const data = await r.json();
    // Tolérance : {texte}, {brouillon}, {export} ou chaîne brute
    if (typeof data === "string") return data;
    return data.texte ?? data.brouillon ?? data.export ?? data.contenu ?? JSON.stringify(data, null, 2);
  }
  return await r.text();
}

export const sourceLive: SourceDonnees = {
  nom: "live",
  getSessions: () => j<Session[]>("/api/sessions"),
  getIncidents: () => j<Incident[]>("/api/incidents"),
  getIncident: (id) => j<Incident>(`/api/incidents/${encodeURIComponent(id)}`),
  getLeurres: () => j<Leurre[]>("/api/leurres"),
  getMesures: () => j<Mesures>("/api/mesures"),
  postDecision: async (id, action, analyste) => {
    const r = await fetch(
      BASE + `/api/incidents/${encodeURIComponent(id)}/decision`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action, analyste }),
      }
    );
    if (!r.ok) throw new Error(`decision → ${r.status}`);
  },
  getNis2: (id) => texte(`/api/incidents/${encodeURIComponent(id)}/nis2`),
  getExport: (id, format) =>
    texte(`/api/incidents/${encodeURIComponent(id)}/export?format=${format}`),

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
