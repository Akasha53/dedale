#!/usr/bin/env bash
# Lance le banc d'essai sAIfe : une page à boutons sur 127.0.0.1:8900 (BANC_PORT pour
# changer le port). Le banc ne lance aucun service de lui-même ; c'est le bouton
# « Démarrer tout » de la page qui s'en charge. Rien n'est exposé hors de la machine.
set -euo pipefail

ICI="$(cd "$(dirname "$0")" && pwd)"
PORT="${BANC_PORT:-8900}"

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Le port $PORT est déjà pris. Ouvrir http://127.0.0.1:$PORT ou choisir BANC_PORT." >&2
  exit 1
fi

echo "Banc sAIfe -> http://127.0.0.1:$PORT"
exec python3 -u "$ICI/serveur.py"
