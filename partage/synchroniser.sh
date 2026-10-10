#!/usr/bin/env bash
# Recopie les règles communes dans l'extension Chrome, qui ne peut lire que son
# propre dossier. L'app Mac lit partage/regles-sites.json directement (ou la copie
# rangée dans Dedale.app par app-mac/construire.sh).
set -euo pipefail
ICI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp "$ICI/regles-sites.json" "$ICI/../extension/regles-sites.json"
echo "Règles recopiées dans extension/regles-sites.json"
