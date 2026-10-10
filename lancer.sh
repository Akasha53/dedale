#!/usr/bin/env bash
# Lancement global de Dédale. Chaque agent décommente sa ligne.
# Usage : ./lancer.sh [--seed]
#   --seed : charge des leurres et trois sessions de démo une fois le backend prêt.
set -euo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDS=()

arreter() {
  echo ""
  echo "Arrêt des modules…"
  for pid in "${PIDS[@]:-}"; do
    [ -n "${pid:-}" ] && kill "$pid" 2>/dev/null || true
  done
}
trap arreter EXIT INT TERM

echo "== Dédale =="

# --- backend (agent A, port 8700) : démarré en premier, les autres s'y connectent ---
echo "Backend  -> http://127.0.0.1:8700 (console API + WS)"
( cd "$RACINE/backend" && uv run uvicorn app.main:app --host 127.0.0.1 --port 8700 ) &
PIDS+=($!)

# Attente que le backend réponde (pas de `timeout` sur ce Mac : boucle + curl).
echo -n "Attente du backend"
for _ in $(seq 1 40); do
  if curl -fs "http://127.0.0.1:8700/api/sante" >/dev/null 2>&1; then echo " — prêt"; break; fi
  echo -n "."; sleep 0.5
done

# --- autres modules : chaque propriétaire décommente SA ligne ---
# Surface Orbis Pay (agent B) — HTTP 8701, MCP 8711 :
# ( cd "$RACINE/leurres" && uv run uvicorn app.main:app --host 127.0.0.1 --port 8701 ) &  PIDS+=($!)
# ( cd "$RACINE/leurres" && uv run python mcp_server.py --port 8711 ) &  PIDS+=($!)
#
# Agent interne + passerelle boîte noire (agent C) — 8702 :
# ( cd "$RACINE/interne" && uv run uvicorn app.main:app --host 127.0.0.1 --port 8702 ) &  PIDS+=($!)
#
# Console web du SOC (agent D) — 5173 en dev (sinon servie par le backend sur 8700) :
( cd "$RACINE/console" && npm run dev ) &  PIDS+=($!)
#
# Banc d'attaque et mesures (agent E) — aucun port, lancé à la demande :
# ( cd "$RACINE/attaque" && uv run python banc.py )

# --- seed de démo optionnel ---
if [ "${1:-}" = "--seed" ]; then
  echo "Seed de démonstration…"
  ( cd "$RACINE/backend" && uv run python seed.py "http://127.0.0.1:8700" ) || echo "Seed échoué (backend prêt ?)"
fi

echo "Ctrl-C pour tout arrêter."
wait
