#!/usr/bin/env bash
# Lancement local du backend, des leurres et de la console.
# Usage : ./lancer.sh [--seed]
#   --seed : charge des leurres et trois sessions de démo une fois le backend prêt.
set -euo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDS=()

if [ "$#" -gt 1 ] || { [ "$#" -eq 1 ] && [ "$1" != "--seed" ]; }; then
  echo "Usage : ./lancer.sh [--seed]" >&2
  exit 2
fi

for commande in uv npm python3 curl; do
  if ! command -v "$commande" >/dev/null 2>&1; then
    echo "Commande requise introuvable : $commande" >&2
    exit 1
  fi
done

if [ ! -x "$RACINE/console/node_modules/.bin/vite" ]; then
  echo "Console non préparée : lancez 'cd console && npm ci' avant ./lancer.sh." >&2
  exit 1
fi

# Refuser de raccorder la démo à un ancien processus sans le savoir.
python3 - <<'PY'
import socket
import sys

occupes = []
for port in (8700, 8701, 8711, 5173):
    for hote in ("127.0.0.1", "::1"):
        try:
            with socket.create_connection((hote, port), timeout=0.2):
                occupes.append(str(port))
                break
        except OSError:
            pass
if occupes:
    print("Ports déjà utilisés : " + ", ".join(occupes), file=sys.stderr)
    print("Arrêtez le lancement précédent avant de relancer. Aucun service n'a été modifié.", file=sys.stderr)
    sys.exit(1)
PY

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
PID_BACKEND=${PIDS[0]}

# Attente que le backend réponde (pas de `timeout` sur ce Mac : boucle + curl).
echo -n "Attente du backend"
PRET=0
for _ in $(seq 1 40); do
  if ! kill -0 "$PID_BACKEND" 2>/dev/null; then
    echo " Le backend s'est arrêté au démarrage." >&2
    exit 1
  fi
  if curl --max-time 1 -fs "http://127.0.0.1:8700/api/sante" >/dev/null 2>&1; then
    echo " : prêt"
    PRET=1
    break
  fi
  echo -n "."; sleep 0.5
done
if [ "$PRET" -ne 1 ]; then
  echo " Le backend n'a pas répondu à temps." >&2
  exit 1
fi

# --- autres modules : chaque propriétaire décommente SA ligne ---
# Surface Orbis Pay (agent B) — HTTP 8701, MCP 8711 (un seul process) :
( cd "$RACINE/leurres" && uv run python lancer.py ) &  PIDS+=($!)
#
# Agent interne (agent C) : bibliothèque, pas de serveur. Démo contre le vrai backend :
#   cd interne && uv run python -m orbis.demo --backend-reel
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
