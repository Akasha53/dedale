#!/bin/bash
# Recettes ffmpeg du guide vidéo (GUIDE_VIDEO.md, partie 2). Testées avec ffmpeg 9.0.1 (Homebrew,
# sans libfreetype ni libass : pas de drawtext) sur macOS, 1080p, 30 images par seconde.
#
#   source recettes.sh          # charge les fonctions, ne lance rien
#   bash recettes.sh essai      # rejoue toutes les recettes sur des entrées fabriquées
#
# Règles : aucune commande interactive (</dev/null partout), `perl alarm` à la place de
# `timeout` (absent du Mac), accolades autour de chaque variable (zsh lit « $x:s=… » comme un
# modificateur de substitution), dossier de travail jetable à chemin littéral.

if [ -n "${BASH_SOURCE[0]:-}" ]; then ICI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
else eval 'ICI="$(cd "$(dirname "${(%):-%x}")" && pwd)"'; fi          # zsh
T="${T:-/tmp/saife-video}"            # dossier de travail ; nettoyage : rm -rf /tmp/saife-video
FOND=f5f5f7                           # gris des plans d'interface
ENC=(-c:v libx264 -preset slow -crf 14 -g 30 -pix_fmt yuv420p -colorspace bt709 -color_primaries bt709 -color_trc bt709)

FF() { perl -e 'alarm 900; exec @ARGV' ffmpeg -hide_banner -loglevel error -y "$@" </dev/null; }
duree() { ffprobe -v error -show_entries format=duration -of csv=p=0 "$1" </dev/null; }
calc() { awk "BEGIN{printf \"%.4f\", $1}"; }

# --- 1. carton texte : PNG transparent rendu par la police système (SF Pro) -----------------
# carton_png SORTIE.png "texte|taille|graisse|RRGGBB[|suivi]" ...
carton_png() {
  local sortie="$1"; shift
  perl -e 'alarm 120; exec @ARGV' swift "${ICI}/carton.swift" "${sortie}" 1920 1080 "$@" </dev/null
}
# légende sous la fenêtre d'interface : 48 px, gris, centrée vers y = 1010
legende_png() { carton_png "$1" --decalage 470 "$2|48|regular|3a3a3c"; }
vide_png() { FF -f lavfi -i "color=c=black@0.0:s=1920x1080,format=rgba" -frames:v 1 "$1"; }

# --- 2. masque arrondi (blanc sur noir) -------------------------------------------------------
masque() { # masque LARGEUR HAUTEUR RAYON SORTIE.png
  printf '<svg xmlns="http://www.w3.org/2000/svg" width="%s" height="%s"><rect width="%s" height="%s" fill="#000"/><rect width="%s" height="%s" rx="%s" fill="#fff"/></svg>' \
    "$1" "$2" "$1" "$2" "$1" "$2" "$3" | rsvg-convert -o "$4"
}

# --- 3. plan d'interface : défilement et zoom doux dans la fenêtre, coins arrondis, ombre, légende ---
# [variables] plan_ui ENTREE(.png|.mp4) SORTIE.mp4 DUREE LEGENDE.png|-
#   FIT=crop      (défaut) prend le haut de l'image au format 16:9 ; pour une capture haute (console),
#                 O0 et O1 (0 à 1) font défiler la fenêtre de haut en bas pendant ZD secondes.
#   FIT=contain   pose l'image entière au centre d'un fond PAD (RRGGBB) ; pour une pop-up ou une carte large.
#   Z0 Z1         zoom de départ et d'arrivée ; CX CY : point visé dans la fenêtre de 1600x900 ;
#   CX0 CY0       point visé au départ (800, 450 par défaut) ; CX0=CX et CY0=CY gardent un cadrage fixe.
#   ZD            durée du mouvement (défaut : toute la durée). Courbe 3p²-2p³, proche du standard (0,4 0 0,6 1).
#   VIT           accélération d'un enregistrement (8 = huit fois plus vite).
#   LEG_IN LEG_D LEG_OUT  début et durée du fondu d'entrée de la légende, durée du fondu de sortie
#                 (défaut 0,4 / 0,5 / 0,4 s ; pour un plan de 1,5 s du montage : 0 / 0,15 / 0,1).
plan_ui() {
  local in="$1" out="$2" d="$3" leg="${4:--}"
  local z0="${Z0:-1}" z1="${Z1:-1}" cx="${CX:-800}" cy="${CY:-450}" zd="${ZD:-$3}" vit="${VIT:-1}"
  local cx0="${CX0:-800}" cy0="${CY0:-450}"
  local o0="${O0:-0}" o1="${O1:-0}" fit="${FIT:-crop}" pad="${PAD:-ffffff}" zn E Eo pre cadre
  local li="${LEG_IN:-0.4}" ld="${LEG_D:-0.5}" lo="${LEG_OUT:-0.4}"
  local -a src
  zn=$(calc "${zd}*30-1")
  E="(st(0,min(1,on/${zn}));ld(0)*ld(0)*(3-2*ld(0)))"
  Eo="(st(1,min(1,t/${zd}));ld(1)*ld(1)*(3-2*ld(1)))"
  pre=""
  if [ "${vit}" != "1" ]; then pre="setpts=PTS/${vit},fps=30,"; fi
  if [ "${fit}" = "contain" ]; then
    cadre="pad=w='max(iw,ih*16/9)':h='max(ih,max(iw,ih*16/9)*9/16)':x='(ow-iw)/2':y='(oh-ih)/2':color=0x${pad}"
  else
    cadre="crop=iw:iw*9/16:0:'(ih-iw*9/16)*(${o0}+(${o1}-${o0})*${Eo})'"
  fi
  case "${in}" in
    *.png|*.jpg) src=(-loop 1 -framerate 30 -t "${d}" -i "${in}") ;;
    *)           src=(-i "${in}") ;;
  esac
  [ "${leg}" = "-" ] && { vide_png "${T}/vide.png"; leg="${T}/vide.png"; }
  [ -f "${T}/masque-ui.png" ] || masque 1600 900 28 "${T}/masque-ui.png"
  FF "${src[@]}" -loop 1 -framerate 30 -i "${T}/masque-ui.png" \
     -f lavfi -i "color=c=black:s=1600x900:r=30" -f lavfi -i "color=c=0x${FOND}:s=1920x1080:r=30" \
     -loop 1 -framerate 30 -t "${d}" -i "${leg}" \
     -filter_complex "[0:v]${pre}${cadre},scale=3200:1800:flags=lanczos,zoompan=z='${z0}+(${z1}-${z0})*${E}':x='max(0,min(iw-iw/zoom,(${cx0}+(${cx}-${cx0})*${E})*2-iw/zoom/2))':y='max(0,min(ih-ih/zoom,(${cy0}+(${cy}-${cy0})*${E})*2-ih/zoom/2))':d=1:s=1600x900:fps=30,format=rgba[ui];\
[1:v]format=gray,split[m1][m2];[ui][m1]alphamerge[rond];\
[2:v]format=rgba[noir];[noir][m2]alphamerge,pad=1800:1100:100:100:color=black@0,gblur=sigma=30,colorchannelmixer=aa=0.18[ombre];\
[3:v][ombre]overlay=60:-40[a];[a][rond]overlay=160:40[b];\
[4:v]format=rgba,fade=t=in:st=${li}:d=${ld}:alpha=1,fade=t=out:st=$(calc "${d}-${lo}"):d=${lo}:alpha=1[c];\
[b][c]overlay=0:'12*pow(1-min(1,max(0,(t-${li})/${ld})),3)':format=auto,format=yuv420p" \
     -t "${d}" "${ENC[@]}" "${out}"
}

# --- 4. carton plein écran : fond blanc, fondu et montée de 14 px --------------------------------
# plan_carton CARTON.png SORTIE.mp4 DUREE [FOND]
plan_carton() {
  local png="$1" out="$2" d="$3" fond="${4:-ffffff}"
  FF -f lavfi -i "color=c=0x${fond}:s=1920x1080:r=30:d=${d}" -loop 1 -framerate 30 -t "${d}" -i "${png}" \
     -filter_complex "[1:v]format=rgba,fade=t=in:st=0.3:d=0.6:alpha=1,fade=t=out:st=$(calc "${d}-0.6"):d=0.5:alpha=1[c];\
[0:v][c]overlay=x=0:y='14*pow(1-min(1,max(0,(t-0.3)/0.6)),3)':format=auto,format=yuv420p" \
     -t "${d}" "${ENC[@]}" "${out}"
}

# --- 5. fondus --------------------------------------------------------------------------------
# fondu_es ENTREE SORTIE DUREE : entrée et sortie de 0,5 s vers le gris de la charte
fondu_es() {
  FF -i "$1" -vf "fade=t=in:st=0:d=0.5:color=0x${FOND},fade=t=out:st=$(calc "$3-0.5"):d=0.5:color=0x${FOND}" "${ENC[@]}" "$2"
}
# enchaine A B SORTIE [TRANSITION DUREE] : fondu enchaîné ; fadewhite pour un changement d'acte
enchaine() {
  local tr="${4:-fade}" du="${5:-0.5}"
  FF -i "$1" -i "$2" -filter_complex "[0:v]settb=AVTB,fps=30,format=yuv420p[a];[1:v]settb=AVTB,fps=30,format=yuv420p[b];\
[a][b]xfade=transition=${tr}:duration=${du}:offset=$(calc "$(duree "$1")-${du}"),format=yuv420p" "${ENC[@]}" "$3"
}

# --- 6. arrêt sur image : le plan se fige, un voile blanc monte, le carton rouge apparaît --------
# arret_sur_image ENTREE SORTIE T_ARRET DUREE_GEL CARTON.png
arret_sur_image() {
  local in="$1" out="$2" t="$3" g="$4" png="$5" tot
  tot=$(calc "${t}+${g}")
  FF -i "${in}" -f lavfi -i "color=c=white:s=1920x1080:r=30,format=rgba,colorchannelmixer=aa=0.86,fade=t=in:st=${t}:d=0.7:alpha=1" \
     -loop 1 -framerate 30 -t "${tot}" -i "${png}" \
     -filter_complex "[0:v]trim=end=${t},setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration=${g},fps=30,format=rgba[v];\
[v][1:v]overlay=shortest=1[w];[2:v]format=rgba,fade=t=in:st=$(calc "${t}+0.5"):d=0.5:alpha=1[c];\
[w][c]overlay=shortest=1:format=auto,format=yuv420p" -t "${tot}" "${ENC[@]}" "${out}"
}

# --- 7. rembobinage de cassette ----------------------------------------------------------------
# rembobine ENTREE SORTIE DUREE_SORTIE [HUD.png]
#   L'entrée est lue à l'envers à 15 i/s et 960x540 (la mémoire de `reverse` est proportionnelle
#   à la durée : 42 s à 1080p30 en prendraient 4 Go), accélérée de 2x à 15x, puis remise en 1080p.
#   Le flou de la mise à l'échelle fait l'effet de bande. HUD : « ◀◀ » en haut à gauche.
rembobine() {
  local in="$1" out="$2" d="$3" hud="${4:--}" A=0.25 M
  M=$(calc "$(duree "${in}")*15")
  [ "${hud}" = "-" ] && { vide_png "${T}/vide.png"; hud="${T}/vide.png"; }
  FF -i "${in}" -f lavfi -i "color=c=gray:s=1920x64:r=30,noise=alls=70:allf=t+u,format=rgba,colorchannelmixer=aa=0.18" \
     -loop 1 -framerate 30 -t "${d}" -i "${hud}" \
     -filter_complex "[0:v]fps=15,scale=960:540,reverse,setpts='(${d}*(-${A}+sqrt(${A}*${A}+4*(1-${A})*N/${M}))/(2*(1-${A})))/TB',fps=30,scale=1920:1080:flags=bicubic,rgbashift=rh=-3:bh=3,noise=alls=6:allf=t,eq=contrast=0.96:saturation=0.9,format=rgba[v];\
[v][1:v]overlay=0:'mod(t*820,1144)-64':shortest=1[w];\
[2:v]format=rgba,fade=t=in:st=0:d=0.3:alpha=1,fade=t=out:st=$(calc "${d}-0.5"):d=0.4:alpha=1[h];\
[w][h]overlay=x=-810:y=-430:shortest=1,format=yuv420p" -t "${d}" "${ENC[@]}" "${out}"
}

# --- 8. écran partagé -----------------------------------------------------------------------------
# ecran_partage GAUCHE.mp4 DROITE.mp4 SORTIE.mp4 DUREE ETIQ_G.png ETIQ_D.png
#   Deux fenêtres de 888x500, coins arrondis, écart de 48 px ; la gauche est désaturée.
ecran_partage() {
  local g="$1" dr="$2" out="$3" d="$4" lg="$5" ld="$6"
  [ -f "${T}/masque-moitie.png" ] || masque 888 500 24 "${T}/masque-moitie.png"
  FF -f lavfi -i "color=c=0x${FOND}:s=1920x1080:r=30:d=${d}" -i "${g}" -i "${dr}" \
     -loop 1 -framerate 30 -i "${T}/masque-moitie.png" -loop 1 -framerate 30 -t "${d}" -i "${lg}" -loop 1 -framerate 30 -t "${d}" -i "${ld}" \
     -filter_complex "[1:v]scale=888:500:force_original_aspect_ratio=increase,crop=888:500,eq=saturation=0.2:brightness=-0.03,format=rgba[g0];\
[2:v]scale=888:500:force_original_aspect_ratio=increase,crop=888:500,format=rgba[d0];\
[3:v]format=gray,split[m1][m2];[g0][m1]alphamerge[g];[d0][m2]alphamerge[d];\
[0:v][g]overlay=48:300:shortest=1[a];[a][d]overlay=984:300:shortest=1[b];\
[b][4:v]overlay=x=-468:y=-300:format=auto[c];[c][5:v]overlay=x=468:y=-300:format=auto,fade=t=in:st=0:d=0.5,format=yuv420p" \
     -t "${d}" "${ENC[@]}" "${out}"
}

# --- 9. accéléré ------------------------------------------------------------------------------------
# accelere ENTREE SORTIE FACTEUR DUREE [BADGE.png] : vitesse constante, images nettes (pas de traînée), pastille ×N
accelere() {
  local in="$1" out="$2" f="$3" d="$4" badge="${5:--}"
  [ "${badge}" = "-" ] && { vide_png "${T}/vide.png"; badge="${T}/vide.png"; }
  FF -i "${in}" -loop 1 -framerate 30 -t "${d}" -i "${badge}" \
     -filter_complex "[0:v]setpts=PTS/${f},fps=30,format=rgba[v];\
[1:v]format=rgba,fade=t=in:st=0:d=0.3:alpha=1,fade=t=out:st=$(calc "${d}-0.5"):d=0.4:alpha=1[l];\
[v][l]overlay=x=770:y=-440:shortest=1,format=yuv420p" -t "${d}" "${ENC[@]}" "${out}"
}
# rampe ENTREE SORTIE DUREE : départ à vitesse normale, accélération continue (même formule que le rembobinage)
rampe() {
  local A=0.25 M
  M=$(calc "$(duree "$1")*15")
  FF -i "$1" -vf "fps=15,setpts='($3*(-${A}+sqrt(${A}*${A}+4*(1-${A})*N/${M}))/(2*(1-${A})))/TB',fps=30,format=yuv420p" -t "$3" "${ENC[@]}" "$2"
}

# --- 10. anneau de clic ---------------------------------------------------------------------------------
# anneau_clic ENTREE SORTIE T0 CX CY : anneau gris qui grandit en 0,45 s et s'efface (CX, CY en pixels 1080p)
anneau_clic() {
  local in="$1" out="$2" t0="$3" cx="$4" cy="$5" d
  d=$(duree "${in}")
  [ -f "${T}/anneau.png" ] || printf '<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240"><circle cx="120" cy="120" r="112" fill="none" stroke="#0d0d0d" stroke-opacity="0.55" stroke-width="8"/></svg>' | rsvg-convert -o "${T}/anneau.png"
  FF -i "${in}" -loop 1 -framerate 30 -t "${d}" -i "${T}/anneau.png" \
     -filter_complex "[1:v]format=rgba,fade=t=out:st=$(calc "${t0}+0.18"):d=0.27:alpha=1,scale=w='max(2,240*(1-pow(1-min(1,max(0,(t-${t0})/0.45)),3)))':h=-2:eval=frame[r];\
[0:v][r]overlay=x='${cx}-overlay_w/2':y='${cy}-overlay_h/2':enable='between(t,${t0},${t0}+0.45)':eval=frame:shortest=1,format=yuv420p" "${ENC[@]}" "${out}"
}

# --- 11. assemblage, musique, export --------------------------------------------------------------------
# assembler LISTE.txt SORTIE.mp4 : concaténation sans réencodage (les plans ont tous le même ENC, 30 i/s, 1080p).
#   La liste contient des lignes « file 'plan01.mp4' », chemins relatifs à la liste.
assembler() { FF -f concat -safe 0 -i "$1" -c copy "$2"; }
# mixer VIDEO.mp4 MUSIQUE.wav SORTIE.mp4 : fondu d'entrée 1,5 s, de sortie 3 s, -16 LUFS, -1,5 dBTP, deux passes
mixer() {
  local v="$1" m="$2" out="$3" d js
  d=$(duree "${v}")
  js="${T}/loudnorm.json"
  perl -e 'alarm 300; exec @ARGV' ffmpeg -hide_banner -nostats -t "${d}" -i "${m}" \
    -af "afade=t=in:st=0:d=1.5,afade=t=out:st=$(calc "${d}-3"):d=3,loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json" -f null - </dev/null 2>&1 | sed -n '/^{/,/^}/p' > "${js}"
  g() { sed -n "s/.*\"$1\" : \"\(.*\)\".*/\1/p" "${js}"; }
  FF -i "${v}" -i "${m}" -map 0:v -map 1:a -c:v copy \
    -af "afade=t=in:st=0:d=1.5,afade=t=out:st=$(calc "${d}-3"):d=3,loudnorm=I=-16:TP=-1.5:LRA=11:measured_I=$(g input_i):measured_TP=$(g input_tp):measured_LRA=$(g input_lra):measured_thresh=$(g input_thresh):offset=$(g target_offset):linear=true" \
    -c:a aac -b:a 256k -ar 48000 -t "${d}" -movflags +faststart "${out}"
}

# --- essai complet ------------------------------------------------------------------------------------------
essai() {
  local S="${1:-${ICI}/../..}"                 # racine du dépôt
  mkdir -p "${T}/essai" && cd "${T}/essai" || return 1
  # entrées fabriquées : une capture fixe, un faux enregistrement d'écran qui défile (30 et 60 i/s)
  cp "${S}/captures/deux-espaces/soc-fraude-en-clair-1440.png" soc.png
  FF -loop 1 -framerate 30 -t 6 -i soc.png -vf "scale=1920:-2:flags=lanczos,crop=1920:1080:0:'(ih-1080)*t/6',format=yuv420p" "${ENC[@]}" rec.mp4
  FF -loop 1 -framerate 60 -t 6 -i soc.png -vf "scale=1920:-2:flags=lanczos,crop=1920:1080:0:'(ih-1080)*t/6',format=yuv420p" -r 60 "${ENC[@]}" rec60.mp4
  carton_png c1.png --fond ffffff "Michèle Delaconta|104|semibold|0d0d0d|-0.02" "Comptable chez Orbis Pay|46|regular|6e6e73"
  carton_png stop.png "Stop.|120|semibold|0d0d0d|-0.02" "Maintenant, avec s*AI*fe.|60|regular|6e6e73"
  carton_png perte.png "48 500 €|130|semibold|c4262e|-0.02" "Le virement est parti.|48|regular|3a3a3c"
  carton_png hud.png "◀◀|84|semibold|0d0d0d"
  carton_png x8.png "×8|64|semibold|6e6e73|-0.01"
  carton_png lg.png --decalage 0 "Sans s*AI*fe|44|semibold|6e6e73"
  carton_png ld.png --decalage 0 "Avec s*AI*fe|44|semibold|0d0d0d"
  legende_png leg1.png "Un mail de la direction."
  plan_carton stop.png p_stop.mp4 3.0
  Z0=1 Z1=1.7 CX=900 CY=560 ZD=3 plan_ui soc.png p_fixe.mp4 4.5 leg1.png
  VIT=1.3 plan_ui rec60.mp4 p_video.mp4 4.5 leg1.png
  O0=0 O1=0.45 ZD=4 plan_ui soc.png p_defile.mp4 4.5 leg1.png
  LEG_IN=0 LEG_D=0.15 LEG_OUT=0.1 plan_ui soc.png p_montage.mp4 1.5 leg1.png
  FIT=contain PAD=f9f9f9 Z0=1 Z1=1.25 plan_ui "${S}/captures/app-theme/apres/popup.png" p_popup.mp4 4.5 leg1.png
  FIT=contain PAD=ffffff plan_ui "${S}/captures/regles/02-regle-active-rendre-les-droits-1440.png" p_regle.mp4 4.5 leg1.png
  arret_sur_image p_video.mp4 p_gel.mp4 3.0 3.0 perte.png
  rembobine p_gel.mp4 p_remb.mp4 2.0 hud.png
  ecran_partage rec.mp4 p_video.mp4 p_split.mp4 4.5 lg.png ld.png
  accelere rec60.mp4 p_x8.mp4 8 0.75 x8.png
  rampe rec.mp4 p_rampe.mp4 3
  anneau_clic rec.mp4 p_clic.mp4 2.0 900 500
  fondu_es p_fixe.mp4 p_fondu.mp4 4.5
  enchaine p_fixe.mp4 p_stop.mp4 p_enchaine.mp4 fadewhite 0.8
  printf "file 'p_stop.mp4'\nfile 'p_fixe.mp4'\nfile 'p_gel.mp4'\n" > liste.txt
  assembler liste.txt assemble.mp4
  mixer assemble.mp4 "${ICI}/musique-essai.wav" final.mp4
  for f in p_stop p_fixe p_montage p_defile p_popup p_regle p_video p_gel p_remb p_split p_x8 p_rampe p_clic p_fondu p_enchaine assemble final; do
    printf "%-12s %6.2f s  " "${f}" "$(duree "${f}.mp4")"; ffprobe -v error -show_entries stream=codec_name,width,height -of csv=p=0 "${f}.mp4" </dev/null | tr '\n' ' '; echo
  done
}

if [ "${1:-}" = "essai" ]; then set -e; mkdir -p "${T}"; essai "${2:-}"; fi
