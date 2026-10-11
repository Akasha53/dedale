#!/bin/bash
# Montage de la vidéo de démo v1 de sAIfe (2 min 15 s, 1080p30, H.264 + AAC).
#
#   bash docs/video/montage-v1.sh            # tous les plans, puis l'assemblage et la musique
#   bash docs/video/montage-v1.sh plans      # les plans seulement
#   bash docs/video/montage-v1.sh final      # assemblage et musique, plans déjà faits
#
# Entrées (voir DECOUPAGE.md) :
#   REC/scene       états de la scène du virement (capture-scene.js)
#   REC/validation  espace /validation, la finance refuse (capture-validation.js)
#   REC/console     console du SOC (captures headless sur un backend isolé)
#   MUSIQUE         musique.py --acte2-fin 64.5 --montage-fin 70.5 --logo 126 --finance 999 --duree 140
# Les recettes ffmpeg viennent de recettes.sh, les cartons de carton.swift.
# Pour une v2 calée sur la voix de Paul : changer les durées dans la liste PLANS en bas, puis
# relancer musique.py avec les nouveaux repères (--acte2-fin, --logo).
#
# Règles : aucune commande interactive, `perl alarm` au lieu de `timeout`, dossiers de travail
# à chemin littéral, aucun `rm` sur une variable.

set -euo pipefail
# awk écrit « 3,9 » sous une locale française, et ffmpeg refuse la virgule
export LC_ALL=en_US.UTF-8 LC_NUMERIC=C
ICI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export T="${T:-/tmp/saife-video-v1/montage}"
REC="${REC:-/tmp/saife-video-v1/rec}"
MUSIQUE="${MUSIQUE:-/tmp/saife-video-v1/musique-v1.wav}"
SORTIE="${SORTIE:-${HOME}/Downloads/sAIfe-demo-v1.mp4}"
CARTON_BIN="${CARTON_BIN:-/tmp/saife-video-v1/bin/carton}"   # swiftc -O carton.swift -o …
mkdir -p "${T}/c" "${T}/p" "${T}/s"
# shellcheck source=recettes.sh
source "${ICI}/recettes.sh"
P="${T}/p"; C="${T}/c"; S="${T}/s"

# carton_png plus rapide si le binaire compilé existe (même rendu que `swift carton.swift`)
if [ -x "${CARTON_BIN}" ]; then
  carton_png() { local s="$1"; shift; perl -e 'alarm 60; exec @ARGV' "${CARTON_BIN}" "${s}" 1920 1080 "$@" </dev/null; }
fi

# suite SORTIE.mp4 "image.png:durée" ... : images fixes en coupe sèche, 3200x1800, 30 i/s
suite() {
  local out="$1"; shift
  local l="${out%.mp4}.txt" dernier=""
  : > "${l}"
  for x in "$@"; do printf "file '%s'\nduration %s\n" "${x%:*}" "${x##*:}" >> "${l}"; dernier="${x%:*}"; done
  printf "file '%s'\n" "${dernier}" >> "${l}"
  FF -f concat -safe 0 -i "${l}" -vf "scale=3200:1800:flags=lanczos,fps=30,format=yuv420p" \
     -c:v libx264 -preset fast -crf 12 -pix_fmt yuv420p "${out}"
}
# fondus SORTIE.mp4 FONDU "image.png:durée" ... : images fixes en fondu enchaîné (durée totale =
# somme des durées moins les fondus)
fondus() {
  local out="$1" f="$2"; shift 2
  local -a ent=(); local filtre="" n=0 cumul=0 prec="n0" dprec=0 x i
  for x in "$@"; do ent+=(-loop 1 -framerate 30 -t "${x##*:}" -i "${x%:*}"); done
  for ((i=0; i<$#; i++)); do filtre="${filtre}[${i}:v]scale=3200:1800,fps=30,format=yuv420p,settb=AVTB[n${i}];"; done
  for x in "$@"; do
    if [ "${n}" -gt 0 ]; then
      cumul=$(calc "${cumul}+${dprec}-${f}")
      filtre="${filtre}[${prec}][n${n}]xfade=transition=fade:duration=${f}:offset=${cumul}[x${n}];"
      prec="x${n}"
    fi
    dprec="${x##*:}"; n=$((n+1))
  done
  FF "${ent[@]}" -filter_complex "${filtre%;}" -map "[${prec}]" -c:v libx264 -preset fast -crf 12 -pix_fmt yuv420p "${out}"
}
# images d'une frappe : toutes les PNG d'un motif, chacune pendant DUREE
frappe() { local motif="$1" d="$2" f; for f in ${motif}; do printf '%s:%s ' "${f}" "${d}"; done; }
leg() { legende_png "${C}/$1.png" "$2"; }

cartons() {
  # 1. ouverture : nom, rôle, mention de fiction (30 px, bas de l'image)
  carton_png "${C}/c01-texte.png" "Michèle Delaconta|104|semibold|0d0d0d|-0.02" "Comptable chez Orbis Pay|46|regular|6e6e73"
  carton_png "${C}/c01-mention.png" --decalage 430 "Personnage et entreprise fictifs.|30|regular|8e8e93"
  FF -i "${C}/c01-texte.png" -i "${C}/c01-mention.png" -filter_complex "overlay=format=auto" "${C}/c01.png"
  carton_png "${C}/c06.png" "41 760 €|130|semibold|c4262e|-0.02" "partis sur le compte d'un escroc.|48|regular|3a3a3c"
  carton_png "${C}/c08.png" "Stop.|120|semibold|0d0d0d|-0.02" "Maintenant, avec s*AI*fe.|60|regular|6e6e73"
  carton_png "${C}/c14.png" "41 760 €|130|semibold|0f7b55|-0.02" "restés chez Orbis Pay.|48|regular|3a3a3c"
  carton_png "${C}/hud.png" "◀◀|84|semibold|0d0d0d"
  # logo : la marque (console/src/assets/dedale.svg, le nouveau logo) au-dessus du logotype
  rsvg-convert -w 200 -h 200 "${ICI}/../../console/src/assets/dedale.svg" -o "${C}/marque.png"
  carton_png "${C}/logo-texte.png" --decalage 150 "s*AI*fe|104|regular|0d0d0d|-0.02" "Salariés prévenus. Agents IA retenus.|46|regular|6e6e73"
  FF -i "${C}/logo-texte.png" -i "${C}/marque.png" -filter_complex "overlay=(W-w)/2:330:format=auto" "${C}/c-logo.png"
  # légendes sous la fenêtre (48 px, gris)
  leg l02 "Un mail d'un fournisseur habituel."
  leg l03 "Il change de RIB."
  leg l04 "Elle prépare le virement."
  leg l05 "Elle l'envoie."
  leg l09 "Même mail, même virement."
  leg l10 "Cette fois, sAIfe le retient."
  leg l11 "Elle sait pourquoi."
  leg l12 "La finance reçoit la demande."
  leg l13 "Elle appelle Atelier Nord et refuse."
  leg l15 "Un agent IA lit un mail piégé."
  leg l16 "La consigne cachée, surlignée."
  leg l17 "L'analyste coupe l'agent."
  leg l18 "Une règle, écrite en français."
  leg l19 "Un agent la prépare et se ferme."
  leg l20 "Les droits en trop partent en un clic."
  leg l21 "L'agent retente d'ouvrir le coffre : refusé."
  leg l22 "Il prévient aussi sur les sites sosies."
  leg l23 "Et met de côté les fichiers piégés."
  leg l24 "Chaque décision est scellée."
  leg l25 "Une page pour le RSSI."
  leg l26 "Exports ECS, Sigma et CEF pour le SIEM."
  leg l27 "La sécurité voit un pseudonyme, pas un nom."
  leg l28 "Le salarié voit ce que sAIfe lit."
}

SC="${REC}/scene"; VA="${REC}/validation"; CO="${REC}/console"
# coordonnées : CX, CY dans la fenêtre de 1600x900 ; anneau de clic en pixels 1080p (fenêtre à 160,40)
BTN_X=970; BTN_Y=619

plans() { plans_histoire; plans_console; plans_logo; }

plans_histoire() {
  # ---- acte 1 : sans sAIfe ----------------------------------------------------------------
  plan_carton "${C}/c01.png" "${P}/01.mp4" 4.5
  fondus "${S}/02.mp4" 0.35 "${SC}/m0-boite.png:1.4" "${SC}/m1-banniere.png:1.9" "${SC}/m2-ouvert.png:1.9"
  Z0=1 Z1=1.06 CX=1000 CY=420 plan_ui "${S}/02.mp4" "${P}/02.mp4" 4.5 "${C}/l02.png"
  Z0=1 Z1=1.7 CX=1016 CY=355 ZD=3 plan_ui "${SC}/m2-ouvert.png" "${P}/03.mp4" 4.5 "${C}/l03.png"
  # shellcheck disable=SC2046
  suite "${S}/04.mp4" "${SC}/b0-vide.png:0.6" $(frappe "${SC}/t0*.png" 0.0833) "${SC}/b1-plein.png:1.35"
  plan_ui "${S}/04.mp4" "${P}/04.mp4" 4.5 "${C}/l04.png"
  suite "${S}/05.mp4" "${SC}/b1-plein.png:1.2" "${SC}/b2-survol.png:2.1" "${SC}/b3-envoye.png:1.2"
  plan_ui "${S}/05.mp4" "${S}/05-ui.mp4" 4.5 "${C}/l05.png"
  anneau_clic "${S}/05-ui.mp4" "${P}/05.mp4" 3.0 "${BTN_X}" "${BTN_Y}"
  # arrêt sur image à la fin du plan 5 (22,5 s), 6 s de gel, carton rouge
  arret_sur_image "${P}/05.mp4" "${P}/0506.mp4" 4.5 6.0 "${C}/c06.png"
  # rembobinage : l'acte 1 lu à l'envers jusqu'au blanc de l'ouverture
  printf "file '01.mp4'\nfile '02.mp4'\nfile '03.mp4'\nfile '04.mp4'\nfile '05.mp4'\n" > "${P}/acte1.txt"
  assembler "${P}/acte1.txt" "${S}/acte1.mp4"
  rembobine "${S}/acte1.mp4" "${S}/07.mp4" 4.5 "${C}/hud.png"
  # le rembobinage sort parfois une image de moins : on garde la dernière pour tomber à 4,5 s pile
  FF -i "${S}/07.mp4" -vf "tpad=stop_mode=clone:stop_duration=0.2,format=yuv420p" -t 4.5 "${ENC[@]}" "${P}/07.mp4"
  # ---- acte 2 : avec sAIfe ----------------------------------------------------------------
  plan_carton "${C}/c08.png" "${P}/08.mp4" 4.5
  # shellcheck disable=SC2046
  suite "${S}/09.mp4" "${SC}/m2-ouvert.png:1.5" "${SC}/b0-vide.png:0.3" $(frappe "${SC}/t0*.png" 0.05) "${SC}/b1-plein.png:1.15"
  plan_ui "${S}/09.mp4" "${P}/09.mp4" 4.5 "${C}/l09.png"
  suite "${S}/10.mp4" "${SC}/b1-plein.png:0.6" "${SC}/b2-survol.png:0.9" "${SC}/b4-verifie.png:1.2" "${SC}/b5-retenu.png:1.8"
  plan_ui "${S}/10.mp4" "${S}/10-ui.mp4" 4.5 "${C}/l10.png"
  anneau_clic "${S}/10-ui.mp4" "${P}/10.mp4" 1.2 "${BTN_X}" "${BTN_Y}"
  Z0=1 Z1=1.9 CX=1360 CY=250 ZD=3 plan_ui "${SC}/b5-retenu.png" "${P}/11.mp4" 4.5 "${C}/l11.png"
  Z0=1 Z1=1.35 CX=1010 CY=520 plan_ui "${VA}/v0-fiche.png" "${P}/12.mp4" 4.5 "${C}/l12.png"
  # shellcheck disable=SC2046
  suite "${S}/13.mp4" "${VA}/v1-decision.png:0.5" $(frappe "${VA}/f0*.png" 0.0667) "${VA}/v2-pret.png:0.4" "${VA}/v3-refuse.png:1.13"
  Z0=1.55 Z1=1.55 CX=1000 CY=610 CX0=1000 CY0=610 plan_ui "${S}/13.mp4" "${P}/13.mp4" 4.5 "${C}/l13.png"
  plan_carton "${C}/c14.png" "${P}/14.mp4" 4.5
}

plans_logo() {
  # le carton du logo est transparent : on le pose sur du blanc avant les fondus au blanc
  FF -f lavfi -i "color=c=white:s=1920x1080:r=30:d=9" -loop 1 -framerate 30 -t 9 -i "${C}/c-logo.png" \
     -filter_complex "[0:v][1:v]overlay=format=auto,fade=t=in:st=0:d=0.8:color=white,fade=t=out:st=6:d=3:color=white,format=yuv420p" \
     -t 9 "${ENC[@]}" "${P}/99.mp4"
}

# Console du SOC et poste du salarié : les fichiers viennent de REC/console (voir MANIFESTE.txt)
# et de captures/saife/ (app Mac, au nom de sAIfe).
plans_console() {
  local A="${ICI}/../../captures/saife"
  # agent IA piégé : incident, consigne cachée, pré-tri et coupure
  Z0=1 Z1=1.25 CX=960 CY=480 plan_ui "${CO}/a01-incident-ce-qui-sest-passe.png" "${P}/15.mp4" 4.5 "${C}/l15.png"
  Z0=1 Z1=1.3 CX=800 CY=470 plan_ui "${CO}/a03-mail-en-entier.png" "${P}/16.mp4" 4.5 "${C}/l16.png"
  suite "${S}/17.mp4" "${CO}/a02-boite-noire-pretri.png:1.5" "${CO}/a05-motif-saisi.png:1.5" "${CO}/a07-agent-coupe.png:1.5"
  Z0=1.35 Z1=1.35 CX=1300 CY=560 CX0=1300 CY0=560 plan_ui "${S}/17.mp4" "${P}/17.mp4" 4.5 "${C}/l17.png"
  # règle écrite en français, puis l'agent des règles qui naît et se ferme
  # shellcheck disable=SC2046
  suite "${S}/18.mp4" "${CO}/b01-vide.png:0.3" $(frappe "${CO}/b0[2-7]-frappe.png" 0.45)
  Z0=1.4 Z1=1.4 CX=960 CY=650 CX0=960 CY0=650 plan_ui "${S}/18.mp4" "${P}/18.mp4" 3.0 "${C}/l18.png"
  suite "${S}/19.mp4" "${CO}/b08-agent.png:0.5" "${CO}/b12-agent.png:0.5" "${CO}/b16-agent.png:0.5" \
        "${CO}/b19-proposition.png:1.7" "${CO}/b20-appliquee.png:1.3"
  Z0=1.4 Z1=1.4 CX=960 CY=650 CX0=960 CY0=650 plan_ui "${S}/19.mp4" "${P}/19.mp4" 4.5 "${C}/l19.png"
  # droits en trop retirés, puis la tentative bloquée
  # shellcheck disable=SC2046
  suite "${S}/20.mp4" $(frappe "${CO}/c0[2-7]-frappe.png" 0.25) "${CO}/c12-agent.png:0.6" \
        "${CO}/c18-proposition.png:1.4" "${CO}/c20-appliquee.png:1.0"
  Z0=1.15 Z1=1.15 CX=920 CY=500 CX0=920 CY0=500 plan_ui "${S}/20.mp4" "${P}/20.mp4" 4.5 "${C}/l20.png"
  suite "${S}/21.mp4" "${CO}/c22-tentative-bloquee-chaine.png:2.25" "${CO}/c25-fil-refuse-droit-retire-bas.png:2.25"
  Z0=1.2 Z1=1.2 CX=800 CY=650 CX0=800 CY0=650 plan_ui "${S}/21.mp4" "${P}/21.mp4" 4.5 "${C}/l21.png"
  # sites sosies (extension Chrome) et fichiers piégés (app Mac)
  Z0=1 Z1=1.08 plan_ui "${SC}/s0-site-sosie.png" "${P}/22.mp4" 3.0 "${C}/l22.png"
  FIT=contain PAD=f9f9f9 Z0=1 Z1=1.08 plan_ui "${A}/app-telechargement.png" "${P}/23.mp4" 3.0 "${C}/l23.png"
  # journal scellé, rapport d'une page
  Z0=1 Z1=1.25 CX=1000 CY=420 ZD=3 plan_ui "${CO}/d01-journal-intact.png" "${P}/24.mp4" 4.5 "${C}/l24.png"
  Z0=1 Z1=1.3 CX=1032 CY=500 plan_ui "${CO}/d02-rapport-haut.png" "${P}/25.mp4" 4.5 "${C}/l25.png"
  # export SIEM : le menu de la console, puis les extraits ECS et Sigma
  LEG_OUT=0.01 Z0=1.2 Z1=1.35 CX=1300 CY=600 plan_ui "${CO}/e01-menu-exporter.png" "${P}/26.mp4" 3.0 "${C}/l26.png"
  LEG_IN=0 LEG_D=0.04 Z0=1 Z1=1.06 plan_ui "${CO}/e03-export-ecs-sigma.png" "${P}/26b.mp4" 3.0 "${C}/l26.png"
  # vie privée : pseudonyme côté SOC, transparence côté salarié
  Z0=1 Z1=1.3 CX=880 CY=433 plan_ui "${CO}/f01-salaries-en-direct.png" "${P}/27.mp4" 4.5 "${C}/l27.png"
  FIT=contain PAD=f9f9f9 Z0=1 Z1=1.12 CX=800 CY=430 plan_ui "${A}/app-transparence.png" "${P}/28.mp4" 6.0 "${C}/l28.png"
}

PLANS=(01 02 03 04 0506 07 08 09 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 26b 27 28 99)

final() {
  : > "${P}/liste.txt"
  for n in "${PLANS[@]}"; do printf "file '%s.mp4'\n" "${n}" >> "${P}/liste.txt"; done
  assembler "${P}/liste.txt" "${T}/assemble.mp4"
  # un seul réencodage à la fin, plus léger que les plans (crf 14) : le fichier reste sous 50 Mo
  FF -i "${T}/assemble.mp4" -c:v libx264 -preset slow -crf 20 -g 60 -pix_fmt yuv420p \
     -colorspace bt709 -color_primaries bt709 -color_trc bt709 -an "${T}/assemble-leger.mp4"
  mixer "${T}/assemble-leger.mp4" "${MUSIQUE}" "${SORTIE}"
  printf "%s : %s s\n" "${SORTIE}" "$(duree "${SORTIE}")"
}

case "${1:-tout}" in
  cartons) cartons ;;
  plans) cartons; plans ;;
  histoire) plans_histoire ;;
  console) plans_console ;;
  logo) plans_logo ;;
  final) final ;;
  tout) cartons; plans; final ;;
esac
