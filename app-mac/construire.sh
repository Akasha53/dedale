#!/usr/bin/env bash
# Construit Dedale.app (application de barre de menus) dans app-mac/.
# Usage : ./construire.sh [--lancer]
# DEDALE_APP_SORTIE construit l'app dans un autre dossier, et DEDALE_SWIFT_SCRATCH compile
# ailleurs que dans .build/ : de quoi vérifier la construction sans toucher à l'app qui tourne.
set -euo pipefail

ICI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ICI"

SCRATCH=()
if [ -n "${DEDALE_SWIFT_SCRATCH:-}" ]; then SCRATCH=(--scratch-path "$DEDALE_SWIFT_SCRATCH"); fi
swift build -c release ${SCRATCH[@]+"${SCRATCH[@]}"}
BIN="$(swift build -c release ${SCRATCH[@]+"${SCRATCH[@]}"} --show-bin-path)/Dedale"
SORTIE="${DEDALE_APP_SORTIE:-$ICI}"
mkdir -p "$SORTIE"
APP="$SORTIE/Dedale.app"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"
cp "$BIN" "$APP/Contents/MacOS/Dedale"
cp "$ICI/Ressources/Info.plist" "$APP/Contents/Info.plist"
# Logo : icône de l'app (CFBundleIconFile), icône de barre de menus en gabarit et logo
# d'en-tête des fenêtres, copiés depuis design/logo/ dans Ressources/.
mkdir -p "$APP/Contents/Resources"
cp "$ICI/Ressources/AppIcon.icns" "$ICI"/Ressources/LogoEntete*.png "$ICI"/Ressources/MenuBarIcon*.png "$APP/Contents/Resources/"
# Règles communes des sites louches, les mêmes que l'extension Chrome.
mkdir -p "$APP/Contents/Resources"
cp "$ICI/../partage/regles-sites.json" "$APP/Contents/Resources/regles-sites.json"
# Configuration MCP factice lue par le module Agents IA tant que le scan réel est coupé.
mkdir -p "$APP/Contents/Resources"
cp -R "$ICI/demo/agents-factices" "$APP/Contents/Resources/agents-factices"
# Signature ad hoc : suffit pour lancer l'app sur ce Mac.
codesign --force --sign - "$APP" >/dev/null 2>&1 || echo "Signature ad hoc impossible, l'app reste lançable en local."
echo "Construit : $APP"

if [ "${1:-}" = "--lancer" ]; then
  open "$APP"
fi
