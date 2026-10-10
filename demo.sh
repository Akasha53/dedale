#!/usr/bin/env bash
# ./demo.sh          démo en deux terminaux (services lancés par ./lancer.sh), choix interactifs
# ./demo.sh jury     démo du jury en une commande : base neuve, services, scènes, chrono
# ./demo.sh jury --arreter   arrête le backend et la console lancés par la démo du jury
set -euo pipefail

racine_dedale="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
script="demo_commune.py"
if [ "${1:-}" = "jury" ]; then
  shift
  script="demo_jury.py"
fi
exec uv run --project "$racine_dedale/interne" python -u "$racine_dedale/scripts/$script" "$@"
