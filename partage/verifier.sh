#!/usr/bin/env bash
# Vérifie les règles communes des deux côtés, sur le même corpus :
#   1. tests de l'extension (node --test), corpus compris ;
#   2. moteur Swift de l'app Mac, compilé à part avec swiftc, sur le même corpus ;
#   3. comparaison adresse par adresse : les deux doivent rendre la même chose.
set -euo pipefail
ICI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RACINE="$(cd "$ICI/.." && pwd)"
TEMP="$(mktemp -d "${TMPDIR:-/tmp}/dedale-sites-XXXXXX")"
trap 'rm -rf "${TEMP:?}"' EXIT

echo "== Extension (node --test)"
(cd "$RACINE/extension" && node --test tests/comparateur.test.js 2>&1 | grep -E "^ℹ (tests|pass|fail)|^✖" )

echo "== App Mac (swiftc)"
swiftc -O -o "$TEMP/essai-sites" \
  "$RACINE/app-mac/Sources/Dedale/SitesRegles.swift" "$RACINE/app-mac/TestsSites/main.swift"
"$TEMP/essai-sites" "$ICI/regles-sites.json" "$ICI/corpus-sites.json" "$TEMP/swift.jsonl"

echo "== Comparaison"
node "$ICI/comparer.mjs" "$TEMP/swift.jsonl"
