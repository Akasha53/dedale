#!/usr/bin/env bash
# Lance la boîte de démo Mailpit sur 127.0.0.1 (rien n'est exposé dehors). Idempotent :
# une boîte déjà lancée est laissée telle quelle.
#
#   ./demarrer.sh             boîte seule : API et interface web 8716, SMTP 8717
#   ./demarrer.sh --service   boîte + service de verdicts (FastAPI, 8715)
#   ./demarrer.sh --arreter   arrête la boîte et le service lancés par ce script
#
# Ports surchargeables : MESSAGERIE_PORT_WEB, MESSAGERIE_PORT_SMTP, MESSAGERIE_PORT.
set -euo pipefail

ICI="$(cd "$(dirname "$0")" && pwd)"
ETAT="$ICI/.boite"
PORT_WEB="${MESSAGERIE_PORT_WEB:-8716}"
PORT_SMTP="${MESSAGERIE_PORT_SMTP:-8717}"
PORT_SERVICE="${MESSAGERIE_PORT:-8715}"
mkdir -p "$ETAT"

pris() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

arreter_pid() {
  local fichier="$1"
  if [[ -f "$fichier" ]]; then
    local pid
    pid="$(cat "$fichier")"
    if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid"
      for _ in $(seq 1 50); do
        kill -0 "$pid" 2>/dev/null || break
        sleep 0.1
      done
      echo "arrêté : PID $pid"
    fi
    : > "$fichier"
  fi
}

if [[ "${1:-}" == "--arreter" ]]; then
  arreter_pid "$ETAT/service.pid"
  arreter_pid "$ETAT/mailpit.pid"
  exit 0
fi

# --- Boîte Mailpit ----------------------------------------------------------------------
if curl -fsS --max-time 2 "http://127.0.0.1:$PORT_WEB/api/v1/info" >/dev/null 2>&1; then
  echo "boîte déjà lancée : http://127.0.0.1:$PORT_WEB (SMTP 127.0.0.1:$PORT_SMTP)"
else
  if ! command -v mailpit >/dev/null 2>&1; then
    echo "Mailpit manque. L'installer avec : brew install mailpit" >&2
    exit 1
  fi
  for p in "$PORT_WEB" "$PORT_SMTP"; do
    if pris "$p"; then
      echo "Le port $p est déjà pris par un autre programme." >&2
      exit 1
    fi
  done
  nohup mailpit \
    --listen "127.0.0.1:$PORT_WEB" \
    --smtp "127.0.0.1:$PORT_SMTP" \
    --database "$ETAT/mailpit.db" \
    --max 500 \
    --disable-version-check \
    --smtp-disable-rdns \
    --block-remote-css-and-fonts \
    >"$ETAT/mailpit.log" 2>&1 </dev/null &
  echo $! > "$ETAT/mailpit.pid"
  for _ in $(seq 1 50); do
    curl -fsS --max-time 1 "http://127.0.0.1:$PORT_WEB/api/v1/info" >/dev/null 2>&1 && break
    sleep 0.2
  done
  if ! curl -fsS --max-time 2 "http://127.0.0.1:$PORT_WEB/api/v1/info" >/dev/null 2>&1; then
    echo "Mailpit ne répond pas. Journal : $ETAT/mailpit.log" >&2
    exit 1
  fi
  echo "boîte lancée : http://127.0.0.1:$PORT_WEB (SMTP 127.0.0.1:$PORT_SMTP)"
fi

# --- Service de verdicts (facultatif) ---------------------------------------------------
if [[ "${1:-}" == "--service" ]]; then
  if curl -fsS --max-time 2 "http://127.0.0.1:$PORT_SERVICE/sante" >/dev/null 2>&1; then
    echo "service déjà lancé : http://127.0.0.1:$PORT_SERVICE"
    exit 0
  fi
  if pris "$PORT_SERVICE"; then
    echo "Le port $PORT_SERVICE est déjà pris par un autre programme." >&2
    exit 1
  fi
  cd "$ICI"
  uv sync -q --inexact </dev/null
  MESSAGERIE_MAILPIT="http://127.0.0.1:$PORT_WEB" nohup "$ICI/.venv/bin/python" -m uvicorn service:app \
    --host 127.0.0.1 --port "$PORT_SERVICE" >"$ETAT/service.log" 2>&1 </dev/null &
  echo $! > "$ETAT/service.pid"
  for _ in $(seq 1 75); do
    curl -fsS --max-time 1 "http://127.0.0.1:$PORT_SERVICE/sante" >/dev/null 2>&1 && break
    sleep 0.2
  done
  if ! curl -fsS --max-time 2 "http://127.0.0.1:$PORT_SERVICE/sante" >/dev/null 2>&1; then
    echo "Le service ne répond pas. Journal : $ETAT/service.log" >&2
    exit 1
  fi
  echo "service lancé : http://127.0.0.1:$PORT_SERVICE/verdicts"
fi
