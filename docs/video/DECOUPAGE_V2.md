# Vidéo de démo v2 : découpage

Fichier : `~/Downloads/sAIfe-demo-v1.mp4`, 1 min 30 (90,0 s), 1920 × 1080, 30 i/s, H.264 + AAC, ~20 Mo, -16 LUFS. Sans voix, textes en français. La v1 longue (2 min 15) est gardée en `~/Downloads/sAIfe-demo-v1-longue.mp4`. Refaire : `bash docs/video/montage-v2.sh`.

Changements voulus par Guilhem : plus courte et punchy, les agents IA dès les 8 premières secondes, un arrêt sur image dramatique au moment où l'argent part. Mêmes données fictives que la v1 (Orbis Pay, Atelier Nord, Michèle Delaconta au seul premier carton, « Salarié 7751 » dans la console). Captures depuis `~/Downloads/sAIfe-video-v1-sources/`.

Style du guide `docs/GUIDE_VIDEO.md` : grille de 1,5 s (80 BPM), zooms en courbe standard `p²(3-2p)` de 3 à 4,5 s, coupes sèches sauf le rembobinage et les fondus au blanc de la fin, cartons lus au moins 0,3 s/mot, musique à -16 LUFS finissant sur une image calme.

## Trois actes

**1. Le danger (0:00 – 0:25,5).** On ouvre sur la menace, agents IA d'abord.

| N° | Temps | Plan | Texte | Source |
|---|---|---|---|---|
| 1 | 0:00–0:06 | carton d'ouverture | « Vos agents IA ont accès à tout. » / « Un mail piégé les retourne contre vous. » | carton.swift |
| 2 | 0:06–0:09 | incident console | « Un agent IA, détourné. » | a01 (console réelle) |
| 3 | 0:09–0:12 | modale du mail | « Une consigne cachée. » | a03 |
| 4 | 0:12–0:15 | boîte noire | « Il vise le coffre de clés. » | a02 |
| 5 | 0:15–0:18 | mail du fournisseur | « Même piège, un salarié. » | scene m2 (RIB changé) |
| 6 | 0:18–0:21 | banque fictive, clic | « Elle valide le virement. » | scene b1→b3 |
| 7 | 0:21–0:24 | **arrêt sur image dramatique** | « 41 760 € partis. » | arret_dramatique : flash, teinte rouge sombre, secousse, montant qui claque |
| 8 | 0:24–0:25,5 | rembobinage court | ◀◀ | rembobine (1,5 s) |

**2. Avec sAIfe (0:25,5 – 0:43,5).** Le choc « Stop », puis sAIfe arrête les deux menaces.

| N° | Temps | Plan | Texte | Source |
|---|---|---|---|---|
| 9 | 0:25,5–0:28,5 | carton | « Stop. » / « Maintenant, avec sAIfe. » | carton.swift (choc musique) |
| 10 | 0:28,5–0:31,5 | agent coupé | « sAIfe coupe l'agent. » | a07 (accent musique) |
| 11 | 0:31,5–0:34,5 | pop-up Retenu | « Et retient le virement. » | scene b5 (motif réel du relecteur) |
| 12 | 0:34,5–0:37,5 | espace /validation | « La finance vérifie. » | v0 (console réelle) |
| 13 | 0:37,5–0:40,5 | refus de la finance | « Et refuse. » | v3 (Claire Dubois, finance ; décision réelle) |
| 14 | 0:40,5–0:43,5 | carton | « 41 760 € » (vert) / « restés chez Orbis Pay. » | carton.swift |

**3. Le reste du produit, puis le logo (0:43,5 – 1:30).** Rafale de 1,5 s, puis les livrables tenus, puis le logo.

| N° | Temps | Plan | Texte | Source |
|---|---|---|---|---|
| 15–19 | 0:43,5–0:51 | rafale 1,5 s | « Règle en français » · « Droits retirés » · « Attaque bloquée » · « Site sosie » · « Fichier piégé » | b20, c20, c22, s0, app-telechargement |
| 20 | 0:51–0:55,5 | journal scellé | « Chaque décision, scellée. » | d01 |
| 21 | 0:55,5–1:00 | rapport d'une page | « Une page pour le RSSI. » | d02 |
| 22 | 1:00–1:04,5 | exports | « Exporté vers votre SIEM. » | e03 (ECS, Sigma, CEF réels) |
| 23 | 1:04,5–1:07,5 | mesures | « 25 sur 25, en 10 ms. » | f02 |
| 24 | 1:07,5–1:10,5 | salariés | « La sécurité ne voit qu'un pseudonyme. » | f01 (« Salarié 7751 ») |
| 25 | 1:10,5–1:15 | transparence app | « Le salarié voit ce que sAIfe lit. » | app-transparence |
| 26 | 1:15–1:21 | landing | — | landing sAIfe (« Deux cibles. Une vigie. ») |
| 27 | 1:21–1:30 | logo | « sAIfe » / « Salariés prévenus. Agents IA retenus. » | dedale.svg, fondu au blanc |

## Musique

`musique.py --freeze 21.0 --silence-duree 1.5 --rewind 24.0 --stop 25.5 --acte2-debut 28.5 --acte2-fin 43.5 --montage-fin 51.0 --logo 81.0 --finance 34.5 --impact --accent 28.5 --duree 90`, puis `mixer` (-16 LUFS, -1,5 dBTP).

- Choc sourd (`--impact`) sur le gel à 21,0 s, aussitôt suivi d'un silence de 1,5 s (l'argent part, le monde se tait).
- Montée pendant le rembobinage, puis choc + accord de do majeur sur « Stop » à 25,5 s.
- Accent clair à 28,5 s quand sAIfe coupe l'agent.
- Fin sur l'accord tenu du logo, fondu de sortie de 3 s.

## Décisions et écarts

- **Arrêt sur image.** Pivot du film, soigné à la demande de Guilhem : flash blanc d'une image, désaturation + teinte rouge très sombre en 0,4 s, légère secousse amortie, le montant « 41 760 € partis. » qui monte en punch sous le fantôme de l'écran. Tenu 3 s (court, comme demandé), pas de séparation RVB (réservée au rembobinage).
- **Agents IA d'abord.** Le carton d'ouverture et le premier incident agent tiennent les 9 premières secondes.
- **Fraude = faux changement de RIB d'un fournisseur connu** (Atelier Nord, 41 760 €), pour que le geste retenu parte chez la finance (`/validation`) plutôt qu'au SOC.
- **Bug du rapport corrigé** : le film montre le rapport d'INC-0003 (coupé par le scénario, synthèse cohérente), pas celui d'INC-0002 dont la synthèse restait « aucun analyste n'a décidé ».

## Pour la v3 calée sur la voix de Paul

Changer les durées dans `plans_danger`, `plans_saife`, `plans_produit`, la liste `PLANS`, puis relancer `musique.py` avec les repères décalés. Les captures restent valables.
