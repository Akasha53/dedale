#!/usr/bin/env bash
# Construit Dedale.app (application de barre de menus) dans app-mac/.
# Usage : ./construire.sh [--lancer]
set -euo pipefail

ICI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ICI"

swift build -c release
BIN="$(swift build -c release --show-bin-path)/Dedale"
APP="$ICI/Dedale.app"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"
cp "$BIN" "$APP/Contents/MacOS/Dedale"
cp "$ICI/Ressources/Info.plist" "$APP/Contents/Info.plist"
# Signature ad hoc : suffit pour lancer l'app sur ce Mac.
codesign --force --sign - "$APP" >/dev/null 2>&1 || echo "Signature ad hoc impossible, l'app reste lançable en local."
echo "Construit : $APP"

if [ "${1:-}" = "--lancer" ]; then
  open "$APP"
fi
