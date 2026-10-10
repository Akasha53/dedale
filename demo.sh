#!/usr/bin/env bash
set -euo pipefail

racine_dedale="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec uv run --project "$racine_dedale/interne" python -u "$racine_dedale/scripts/demo_commune.py" "$@"
