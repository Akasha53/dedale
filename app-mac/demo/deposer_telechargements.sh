#!/usr/bin/env bash
# Dépose trois faux téléchargements inoffensifs, avec une provenance simulée, pour la démo
# du module Téléchargements de Dédale :
#   - « Facture-octobre.pdf.app » : paquet d'application sans programme, venu de
#     factures-orbis.example (double extension) ;
#   - « Releve-de-compte.docm » : document Word avec un projet VBA vide, reçu par mail de
#     orbis-pay-facturation.example (macros) ;
#   - « Photos-seminaire.zip » : archive protégée par mot de passe, venue de
#     partage-photos.example.
# Aucun ne contient de code exécutable. La provenance est posée comme le ferait un
# navigateur : attributs com.apple.quarantine et com.apple.metadata:kMDItemWhereFroms.
#
# Usage : ./deposer_telechargements.sh [--dossier <chemin>] [--nettoyer]
#   --dossier   dossier cible (défaut : $DEDALE_TELECHARGEMENTS, sinon ~/Downloads)
#   --nettoyer  retire les trois fichiers du dossier et de « Dédale - mis de côté »
set -euo pipefail

DOSSIER="${DEDALE_TELECHARGEMENTS:-$HOME/Downloads}"
NETTOYER=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dossier) DOSSIER="$2"; shift 2 ;;
    --nettoyer) NETTOYER=1; shift ;;
    *) echo "option inconnue : $1" >&2; exit 2 ;;
  esac
done
DOSSIER="${DOSSIER%/}"
NOMS=("Facture-octobre.pdf.app" "Releve-de-compte.docm" "Photos-seminaire.zip")
COTE="$DOSSIER/Dédale - mis de côté"

if [ "$NETTOYER" = 1 ]; then
  for nom in "${NOMS[@]}"; do
    for ou in "$DOSSIER" "$COTE"; do
      if [ -e "$ou/$nom" ]; then rm -rf "${ou:?}/${nom:?}"; echo "retiré : $ou/$nom"; fi
    done
  done
  rmdir "$COTE" 2>/dev/null || true
  exit 0
fi

[ -d "$DOSSIER" ] || { echo "dossier introuvable : $DOSSIER" >&2; exit 1; }
TRAVAIL="$(mktemp -d "${TMPDIR:-/tmp}/dedale-demo.XXXXXX")"
trap 'rm -rf "${TRAVAIL:?}"' EXIT

# Provenance simulée : application et liste d'origines (URL ou expéditeur).
provenance() {
  local fichier="$1" application="$2"; shift 2
  local horodatage uuid plist
  horodatage="$(printf '%x' "$(date +%s)")"
  uuid="$(uuidgen)"
  xattr -w com.apple.quarantine "0081;${horodatage};${application};${uuid}" "$fichier"
  plist="$TRAVAIL/origines.plist"
  {
    echo '<?xml version="1.0" encoding="UTF-8"?>'
    echo '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
    echo '<plist version="1.0"><array>'
    for origine in "$@"; do
      printf '<string>%s</string>\n' "$(printf '%s' "$origine" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g')"
    done
    echo '</array></plist>'
  } > "$plist"
  plutil -convert binary1 -o "$plist.bin" "$plist"
  xattr -wx com.apple.metadata:kMDItemWhereFroms "$(xxd -p "$plist.bin" | tr -d '\n')" "$fichier"
}

# 1. Paquet d'application sans exécutable : il ne peut rien lancer.
APP="$TRAVAIL/Facture-octobre.pdf.app"
mkdir -p "$APP/Contents/Resources"
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleIdentifier</key><string>example.dedale.demo.facture</string>
  <key>CFBundleName</key><string>Facture-octobre</string>
  <key>CFBundlePackageType</key><string>APPL</string>
</dict></plist>
PLIST
echo "Fichier de démonstration Dédale : aucun programme, rien ne s'exécute." > "$APP/Contents/Resources/README.txt"
provenance "$APP" "Safari" \
  "https://cdn.factures-orbis.example/telechargement/Facture-octobre.pdf.app" \
  "https://factures-orbis.example/espace-client"

# 2. Document Word avec un projet VBA vide.
DOCM="$TRAVAIL/docm"
mkdir -p "$DOCM/word" "$DOCM/_rels"
echo '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>' > "$DOCM/[Content_Types].xml"
echo '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>' > "$DOCM/word/document.xml"
echo "Projet VBA vide : fichier de démonstration Dédale, sans aucune macro." > "$DOCM/word/vbaProject.bin"
(cd "$DOCM" && zip -q -X -r "$TRAVAIL/Releve-de-compte.docm" .)
provenance "$TRAVAIL/Releve-de-compte.docm" "Mail" \
  "Service facturation <facturation@orbis-pay-facturation.example>" \
  "message:%3Cdemo-releve@orbis-pay-facturation.example%3E"

# 3. Archive protégée par mot de passe (le mot de passe ne sert qu'à la démo).
echo "Photos du séminaire : fichier de démonstration Dédale." > "$TRAVAIL/photos.txt"
(cd "$TRAVAIL" && zip -q -X -P "demo-dedale" "$TRAVAIL/Photos-seminaire.zip" photos.txt)
provenance "$TRAVAIL/Photos-seminaire.zip" "Google Chrome" \
  "https://partage-photos.example/s/seminaire/Photos-seminaire.zip"

for nom in "${NOMS[@]}"; do
  if [ -e "$DOSSIER/$nom" ]; then
    echo "déjà présent, ignoré : $DOSSIER/$nom (relancer avec --nettoyer)" >&2
    continue
  fi
  mv "$TRAVAIL/$nom" "$DOSSIER/$nom"
  echo "déposé : $DOSSIER/$nom"
  sleep 1.5
done
