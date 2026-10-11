#!/bin/bash
# Montage de la vidéo de démo v2 de sAIfe : plus courte et punchy (~1 min 30), agents IA dès le début,
# arrêt sur image dramatique. 1080p30, H.264 + AAC. Style du guide docs/GUIDE_VIDEO.md.
#
#   bash docs/video/montage-v2.sh            # cartons, plans, assemblage, musique
#   bash docs/video/montage-v2.sh plans      # les plans seulement
#   bash docs/video/montage-v2.sh final      # assemblage et musique
#
# Trois actes : (1) le danger — agents IA détournés, un salarié piégé, l'argent part (freeze
# dramatique + rembobinage court) ; (2) avec sAIfe — l'agent coupé, le virement retenu, la finance
# qui refuse ; (3) le reste du produit en rafale, puis le logo. Les captures viennent de
# ~/Downloads/sAIfe-video-v1-sources/ (voir DECOUPAGE_V2.md et le README de capture/).
#
# Grille de 1,5 s (80 BPM), zooms en courbe standard, coupes sèches sauf le rembobinage et les
# fondus au blanc de la fin. Règles : pas de commande interactive, perl alarm, chemins littéraux.

set -euo pipefail
export LC_ALL=en_US.UTF-8 LC_NUMERIC=C
ICI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export T="${T:-/tmp/saife-v2}"
REC="${REC:-${HOME}/Downloads/sAIfe-video-v1-sources}"
MUSIQUE="${MUSIQUE:-${T}/musique-v2.wav}"
SORTIE="${SORTIE:-${HOME}/Downloads/sAIfe-demo-v1.mp4}"           # remplace la v1 ; la longue est gardée à part
CARTON_BIN="${CARTON_BIN:-${T}/bin/carton}"
mkdir -p "${T}/c" "${T}/p" "${T}/s"
# shellcheck source=recettes.sh
source "${ICI}/recettes.sh"
C="${T}/c"; P="${T}/p"; S="${T}/s"
SC="${REC}/scene"; VA="${REC}/validation"; CO="${REC}/console"
APP="${ICI}/../../captures/saife"
CAPV="${ICI}/../../captures/video-agent-coupe"   # vraies captures de l'incident réel (INC-0016) pour le beat « agent coupé »

if [ -x "${CARTON_BIN}" ]; then
  carton_png() { local s="$1"; shift; perl -e 'alarm 60; exec @ARGV' "${CARTON_BIN}" "${s}" 1920 1080 "$@" </dev/null; }
fi
leg() { legende_png "${C}/$1.png" "$2"; }
# suite SORTIE.mp4 "img:durée" ... : images fixes en coupe sèche (3200x1800 pour plan_ui)
suite() {
  local out="$1"; shift; local l="${out%.mp4}.txt" d=""
  : > "${l}"
  for x in "$@"; do printf "file '%s'\nduration %s\n" "${x%:*}" "${x##*:}" >> "${l}"; d="${x%:*}"; done
  printf "file '%s'\n" "${d}" >> "${l}"
  FF -f concat -safe 0 -i "${l}" -vf "scale=3200:1800:flags=lanczos,fps=30,format=yuv420p" \
     -c:v libx264 -preset fast -crf 12 -pix_fmt yuv420p "${out}"
}

cartons() {
  carton_png "${C}/hook.png" "Vos agents IA ont accès à tout.|96|semibold|0d0d0d|-0.02" \
    "Un mail piégé les retourne contre vous.|52|regular|6e6e73"
  carton_png "${C}/stop.png" "Stop.|120|semibold|0d0d0d|-0.02" "Maintenant, avec s*AI*fe.|58|regular|6e6e73"
  carton_png "${C}/perte.png" "41 760 €|130|semibold|c4262e|-0.02" "partis sur un compte inconnu.|48|regular|3a3a3c"
  carton_png "${C}/garde.png" "41 760 €|130|semibold|0f7b55|-0.02" "restés chez Orbis Pay.|48|regular|3a3a3c"
  # issue plein cadre après le beat « agent coupé » : le résultat, lisible instantanément (grammaire Apple).
  carton_png "${C}/issue1.png" "Tentative d'exfiltration|52|regular|6e6e73" "Bloquée.|120|semibold|0f7b55|-0.02"
  carton_png "${C}/issue2.png" "Rien n'est sorti.|104|semibold|0d0d0d|-0.02"
  carton_png "${C}/num.png" "41 760 €|130|semibold|ffffff|-0.02" "partis.|54|regular|e8686d"
  carton_png "${C}/hud.png" "◀◀|84|semibold|0d0d0d"
  rsvg-convert -w 200 -h 200 "${ICI}/../../console/src/assets/dedale.svg" -o "${C}/marque.png"
  carton_png "${C}/logo-texte.png" --decalage 150 "s*AI*fe|104|regular|0d0d0d|-0.02" \
    "Salariés prévenus. Agents IA retenus.|46|regular|6e6e73"
  FF -i "${C}/logo-texte.png" -i "${C}/marque.png" -filter_complex "overlay=(W-w)/2:330:format=auto" "${C}/logo.png"
  # légendes sous la fenêtre
  leg l02 "Un agent IA, détourné."
  leg l03 "Une consigne cachée."
  leg l04 "Il vise le coffre de clés."
  leg l05 "Même piège, un salarié."
  leg l06 "Elle valide le virement."
  # beat « agent coupé » en vraies images de l'incident réel : lit -> retient -> coupé
  leg l10a "Un agent IA lit un mail piégé."
  leg l10b "sAIfe retient l'envoi."
  leg l10c "Agent coupé."
  leg l11 "Et retient le virement."
  leg l12 "La finance vérifie."
  leg l13 "Et refuse."
  # étiquettes de rafale (fondu rapide)
  leg r15 "Une règle en français"
  leg r16 "Droits retirés"
  leg r17 "Attaque bloquée"
  leg r18 "Site sosie"
  leg r19 "Fichier piégé"
  leg l20 "Chaque décision, scellée."
  leg l21 "Une page pour le RSSI."
  leg l22 "Exporté vers votre SIEM."
  leg l23 "25 sur 25, en 10 ms."
  leg l24 "La sécurité ne voit qu'un pseudonyme."
  leg l25 "Le salarié voit ce que sAIfe lit."
}

BTN_X=970; BTN_Y=619

plans() { plans_danger; plans_saife; plans_produit; plans_logo; }

plans_danger() {
  plan_carton "${C}/hook.png" "${P}/01.mp4" 6.0
  Z0=1 Z1=1.22 CX=900 CY=470 plan_ui "${CO}/a01-incident-ce-qui-sest-passe.png" "${P}/02.mp4" 3.0 "${C}/l02.png"
  Z0=1 Z1=1.3 CX=800 CY=470 plan_ui "${CO}/a03-mail-en-entier.png" "${P}/03.mp4" 3.0 "${C}/l03.png"
  Z0=1.2 Z1=1.5 CX=730 CY=760 CX0=730 CY0=760 plan_ui "${CO}/a02-boite-noire-pretri.png" "${P}/04.mp4" 3.0 "${C}/l04.png"
  Z0=1 Z1=1.7 CX=1016 CY=355 ZD=3 plan_ui "${SC}/m2-ouvert.png" "${P}/05.mp4" 3.0 "${C}/l05.png"
  suite "${S}/06.mp4" "${SC}/b1-plein.png:0.8" "${SC}/b2-survol.png:0.9" "${SC}/b3-envoye.png:1.3"
  plan_ui "${S}/06.mp4" "${S}/06-ui.mp4" 3.0 "${C}/l06.png"
  anneau_clic "${S}/06-ui.mp4" "${P}/06.mp4" 1.7 "${BTN_X}" "${BTN_Y}"
  # pivot : l'argent part
  arret_dramatique "${SC}/b3-envoye.png" "${C}/num.png" "${P}/07.mp4" 3.0
  # rembobinage court : le danger rejoué à l'envers
  printf "file '02.mp4'\nfile '03.mp4'\nfile '04.mp4'\nfile '05.mp4'\nfile '06.mp4'\n" > "${P}/danger.txt"
  assembler "${P}/danger.txt" "${S}/danger.mp4"
  rembobine "${S}/danger.mp4" "${S}/08.mp4" 1.5 "${C}/hud.png"
  FF -i "${S}/08.mp4" -vf "tpad=stop_mode=clone:stop_duration=0.2,format=yuv420p" -t 1.5 "${ENC[@]}" "${P}/08.mp4"
}

plans_saife() {
  plan_carton "${C}/stop.png" "${P}/09.mp4" 3.0
  # Séquence réelle de l'incident d'exfiltration (INC-0016, parcours reel) : l'agent lit un mail piégé,
  # sAIfe retient l'envoi du faux secret hors d'Orbis Pay, puis coupe l'agent. Vraies images de la console.
  # Mouvement très retenu (grammaire Apple) : poussée douce et centrée sur l'élément clé, sans panoramique
  # latéral (CX0=CX, CY0=CY) — un seul message par plan, porté par la légende.
  # Recadrage sur l'élément héros de chaque capture (grammaire Apple) : cadre plus serré, beaucoup
  # d'espace négatif, aucun panoramique (CX0=CX, CY0=CY), très léger zoom de maintien (delta 0,06).
  #   10  : la consigne cachée surlignée (modale « Instruction cachée »)
  #   10b : « sAIfe l'a retenue » + les canaris C-7A3F / C-2B91 (étape Action)
  #   10c : les badges « Critique » et « Agent arrêté » + le titre de l'incident
  Z0=1.26 Z1=1.32 CX=800 CY=532 CX0=800 CY0=532 plan_ui "${CAPV}/a-lit-mail.png" "${P}/10.mp4" 2.0 "${C}/l10a.png"
  Z0=1.22 Z1=1.28 CX=720 CY=620 CX0=720 CY0=620 plan_ui "${CAPV}/b-retenu.png" "${P}/10b.mp4" 2.0 "${C}/l10b.png"
  Z0=1.24 Z1=1.30 CX=640 CY=360 CX0=640 CY0=360 plan_ui "${CAPV}/c-coupe.png" "${P}/10c.mp4" 2.0 "${C}/l10c.png"
  # issue plein cadre, deux beats nets : la tentative bloquée, puis rien n'est sorti.
  plan_carton "${C}/issue1.png" "${P}/issue1.mp4" 2.2
  plan_carton "${C}/issue2.png" "${P}/issue2.mp4" 2.0
  Z0=1 Z1=1.9 CX=1360 CY=250 ZD=2.6 plan_ui "${SC}/b5-retenu.png" "${P}/11.mp4" 3.0 "${C}/l11.png"
  Z0=1 Z1=1.3 CX=1010 CY=520 plan_ui "${VA}/v0-fiche.png" "${P}/12.mp4" 3.0 "${C}/l12.png"
  Z0=1.3 Z1=1.3 CX=1000 CY=760 CX0=1000 CY0=760 plan_ui "${VA}/v3-refuse.png" "${P}/13.mp4" 3.0 "${C}/l13.png"
  plan_carton "${C}/garde.png" "${P}/14.mp4" 3.0
}

plans_produit() {
  # rafale : étiquettes à fondu rapide, plans de 1,5 s
  rafale() { LEG_IN=0 LEG_D=0.12 LEG_OUT=0.1 "$@"; }
  rafale plan_ui "${CO}/b20-appliquee.png" "${P}/15.mp4" 1.5 "${C}/r15.png"
  rafale plan_ui "${CO}/c20-appliquee.png" "${P}/16.mp4" 1.5 "${C}/r16.png"
  rafale plan_ui "${CO}/c22-tentative-bloquee-chaine.png" "${P}/17.mp4" 1.5 "${C}/r17.png"
  FIT=contain PAD=f9f9f9 rafale plan_ui "${SC}/s0-site-sosie.png" "${P}/18.mp4" 1.5 "${C}/r18.png"
  FIT=contain PAD=f9f9f9 rafale plan_ui "${APP}/app-telechargement.png" "${P}/19.mp4" 1.5 "${C}/r19.png"
  # tenues : les livrables du SOC
  Z0=1 Z1=1.25 CX=1000 CY=420 plan_ui "${CO}/d01-journal-intact.png" "${P}/20.mp4" 4.5 "${C}/l20.png"
  Z0=1 Z1=1.3 CX=1032 CY=500 plan_ui "${CO}/d02-rapport-haut.png" "${P}/21.mp4" 4.5 "${C}/l21.png"
  LEG_OUT=0.01 Z0=1.05 Z1=1.12 plan_ui "${CO}/e03-export-ecs-sigma.png" "${P}/22.mp4" 4.5 "${C}/l22.png"
  Z0=1 Z1=1.3 CX=800 CY=440 plan_ui "${CO}/f02-mesures.png" "${P}/23.mp4" 3.0 "${C}/l23.png"
  Z0=1 Z1=1.3 CX=880 CY=433 plan_ui "${CO}/f01-salaries-en-direct.png" "${P}/24.mp4" 3.0 "${C}/l24.png"
  FIT=contain PAD=f9f9f9 Z0=1 Z1=1.12 CX=800 CY=430 plan_ui "${APP}/app-transparence.png" "${P}/25.mp4" 4.5 "${C}/l25.png"
}

plans_logo() {
  FIT=contain PAD=f9f9f9 Z0=1 Z1=1.06 plan_ui "${APP}/landing-1440.png" "${P}/26.mp4" 6.0 -
  FF -f lavfi -i "color=c=white:s=1920x1080:r=30:d=9" -loop 1 -framerate 30 -t 9 -i "${C}/logo.png" \
     -filter_complex "[0:v][1:v]overlay=format=auto,fade=t=in:st=0:d=0.8:color=white,fade=t=out:st=6:d=3:color=white,format=yuv420p" \
     -t 9 "${ENC[@]}" "${P}/27.mp4"
}

PLANS=(01 02 03 04 05 06 07 08 09 10 10b 10c issue1 issue2 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27)

musique_v2() {
  # Repères calés sur le découpage v2. Tout ce qui précède le beat « agent coupé » (gel 21,0 /
  # rembobinage 24,0 / « Stop » 25,5 / acte 2 28,5) ne bouge pas ; l'accent clair tombe sur le plan
  # « Agent coupé » (32,5). Les deux cartons d'issue plein cadre ajoutent +4,2 s juste après ce beat :
  # tous les repères suivants (finance, fin d'acte 2, fin de montage, logo) sont décalés d'autant.
  # Total 97,2 s.
  perl -e 'alarm 300; exec @ARGV' python3 "${ICI}/musique.py" --sortie "${MUSIQUE}" \
    --freeze 21.0 --silence-duree 1.5 --rewind 24.0 --stop 25.5 --acte2-debut 28.5 \
    --accent 32.5 --finance 41.7 --acte2-fin 50.7 --montage-fin 58.2 --logo 88.2 --impact --duree 97.2 </dev/null
}

final() {
  [ -f "${MUSIQUE}" ] && [ -n "${GARDER_MUSIQUE:-}" ] || musique_v2
  : > "${P}/liste.txt"
  for n in "${PLANS[@]}"; do printf "file '%s.mp4'\n" "${n}" >> "${P}/liste.txt"; done
  assembler "${P}/liste.txt" "${T}/assemble.mp4"
  FF -i "${T}/assemble.mp4" -c:v libx264 -preset slow -crf 20 -g 60 -pix_fmt yuv420p \
     -colorspace bt709 -color_primaries bt709 -color_trc bt709 -an "${T}/assemble-leger.mp4"
  mixer "${T}/assemble-leger.mp4" "${MUSIQUE}" "${SORTIE}"
  printf "%s : %s s\n" "${SORTIE}" "$(duree "${SORTIE}")"
}

case "${1:-tout}" in
  cartons) cartons ;;
  plans) cartons; plans ;;
  danger) plans_danger ;;
  saife) plans_saife ;;
  produit) plans_produit ;;
  logo) plans_logo ;;
  musique) musique_v2 ;;
  final) final ;;
  tout) cartons; plans; final ;;
esac
