# Vidéo de démo v2 : découpage

Fichier : `~/Downloads/sAIfe-demo-v1.mp4`, 1 min 37 (97,2 s), 1920 × 1080, 30 i/s, H.264 + AAC, ~20 Mo, -16 LUFS. Sans voix, textes en français. La v1 longue (2 min 15) est gardée en `~/Downloads/sAIfe-demo-v1-longue.mp4` ; la version d'avant la séquence agent réelle (90 s) en `~/Downloads/sAIfe-demo-v1-avant-sequence-reelle.mp4`. Refaire : `bash docs/video/montage-v2.sh`.

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

**2. Avec sAIfe (0:25,5 – 0:50,7).** Le choc « Stop », puis sAIfe arrête les deux menaces. Les trois plans de preuve sont recadrés sur leur élément héros (cadre serré, espace négatif, zoom de maintien), et le beat « agent coupé » débouche sur deux cartons plein cadre qui disent l'issue noir sur blanc.

| N° | Temps | Plan | Texte | Source |
|---|---|---|---|---|
| 9 | 0:25,5–0:28,5 | carton | « Stop. » / « Maintenant, avec sAIfe. » | carton.swift (choc musique) |
| 10 | 0:28,5–0:30,5 | gros plan sur la consigne cachée surlignée | « Un agent IA lit un mail piégé. » | video-agent-coupe/a-lit-mail (INC-0016 réel) |
| 10b | 0:30,5–0:32,5 | gros plan « sAIfe l'a retenue » + canaris C-7A3F/C-2B91 | « sAIfe retient l'envoi. » | video-agent-coupe/b-retenu (INC-0016 réel) |
| 10c | 0:32,5–0:34,5 | gros plan badges « Critique » / « Agent arrêté » + titre | « Agent coupé. » | video-agent-coupe/c-coupe (INC-0016 réel ; accent musique) |
| issue1 | 0:34,5–0:36,7 | **carton d'issue plein cadre** | « Tentative d'exfiltration » / « Bloquée. » (vert) | carton.swift |
| issue2 | 0:36,7–0:38,7 | **carton d'issue plein cadre** | « Rien n'est sorti. » | carton.swift |
| 11 | 0:38,7–0:41,7 | pop-up Retenu | « Et retient le virement. » | scene b5 (motif réel du relecteur) |
| 12 | 0:41,7–0:44,7 | espace /validation | « La finance vérifie. » | v0 (console réelle) |
| 13 | 0:44,7–0:47,7 | refus de la finance | « Et refuse. » | v3 (Claire Dubois, finance ; décision réelle) |
| 14 | 0:47,7–0:50,7 | carton | « 41 760 € » (vert) / « restés chez Orbis Pay. » | carton.swift |

**3. Le reste du produit, puis le logo (0:50,7 – 1:37,2).** Rafale de 1,5 s, puis les livrables tenus, puis le logo.

| N° | Temps | Plan | Texte | Source |
|---|---|---|---|---|
| 15–19 | 0:50,7–0:58,2 | rafale 1,5 s | « Règle en français » · « Droits retirés » · « Attaque bloquée » · « Site sosie » · « Fichier piégé » | b20, c20, c22, s0, app-telechargement |
| 20 | 0:58,2–1:02,7 | journal scellé | « Chaque décision, scellée. » | d01 |
| 21 | 1:02,7–1:07,2 | rapport d'une page | « Une page pour le RSSI. » | d02 |
| 22 | 1:07,2–1:11,7 | exports | « Exporté vers votre SIEM. » | e03 (ECS, Sigma, CEF réels) |
| 23 | 1:11,7–1:14,7 | mesures | « 25 sur 25, en 10 ms. » | f02 |
| 24 | 1:14,7–1:17,7 | salariés | « La sécurité ne voit qu'un pseudonyme. » | f01 (« Salarié 7751 ») |
| 25 | 1:17,7–1:22,2 | transparence app | « Le salarié voit ce que sAIfe lit. » | app-transparence |
| 26 | 1:22,2–1:28,2 | landing | — | landing sAIfe (« Deux cibles. Une vigie. ») |
| 27 | 1:28,2–1:37,2 | logo | « sAIfe » / « Salariés prévenus. Agents IA retenus. » | dedale.svg, fondu au blanc |

## Musique

`musique.py --freeze 21.0 --silence-duree 1.5 --rewind 24.0 --stop 25.5 --acte2-debut 28.5 --accent 32.5 --finance 41.7 --acte2-fin 50.7 --montage-fin 58.2 --logo 88.2 --impact --duree 97.2`, puis `mixer` (-16 LUFS, -1,5 dBTP). `montage-v2.sh` la génère tout seul dans `final()` (fonction `musique_v2`).

- Choc sourd (`--impact`) sur le gel à 21,0 s, aussitôt suivi d'un silence de 1,5 s (l'argent part, le monde se tait).
- Montée pendant le rembobinage, puis choc + accord de do majeur sur « Stop » à 25,5 s.
- Accent clair à 32,5 s sur le plan « Agent coupé » (fin de la séquence agent réelle lit → retient → coupé). Les deux cartons d'issue qui suivent tombent dans un temps tenu, sans nouvel accent : la grammaire Apple laisse le verdict respirer en silence.
- Fin sur l'accord tenu du logo, fondu de sortie de 3 s.

Tout ce qui est avant le beat « agent coupé » ne bouge pas (gel 21,0, rembobinage 24,0, « Stop » 25,5, acte 2 28,5, accent 32,5). Les deux cartons d'issue plein cadre ajoutent 4,2 s juste après ce beat ; les repères suivants (finance, fin d'acte 2, fin de montage, logo) sont décalés d'autant, total 97,2 s.

## Décisions et écarts

- **Séquence agent réelle (plans 10/10b/10c).** À la demande du fondateur, le beat « agent coupé » montre désormais le vrai parcours en images de la console, pas un seul plan de fin. Trois plans de 2 s tirés d'un incident d'exfiltration réel ouvert par `orbis.demo --scenario reel` (modèle local qwen2.5:7b, INC-0016) : l'agent lit un mail piégé (modale, consigne cachée surlignée), sAIfe retient l'envoi du faux secret hors d'Orbis Pay (étape Action, canaris C-7A3F/C-2B91), puis l'agent est coupé (« Agent arrêté, rien n'est sorti »). Captures dans `captures/video-agent-coupe/` (script `capture/console-agent-coupe.js`, proxy Vite 5173 qui signe les requêtes). La console dit l'exfiltration en clair (« emporte un faux secret … vers une adresse hors d'Orbis Pay », « sortie de données ») ; la mention littérale « Tentative d'exfiltration : oui » vit dans la donnée de l'incident et le rapport, pas dans ces écrans.
- **Issue lisible plein cadre (passe Apple).** À la demande du fondateur, le beat « agent coupé » débouche sur deux cartons plein cadre qui disent le résultat noir sur blanc : « Tentative d'exfiltration » / « Bloquée. » (vert, même 0f7b55 que le carton garde), puis « Rien n'est sorti. ». L'information vivait dans la donnée de l'incident (« sortie de données », rapport) mais n'était pas lisible en gros ; elle l'est maintenant, une idée par carton, coupe nette. La légende du plan 10c passe de « Agent coupé. Rien n'est sorti. » à « Agent coupé. » pour ne pas doubler le carton.
- **Recadrage Apple des trois plans de preuve (10/10b/10c).** Au lieu de montrer l'écran entier, chaque plan est cadré serré sur son élément héros, avec beaucoup d'espace négatif, aucun panoramique latéral (CX0=CX, CY0=CY) et un très léger zoom de maintien (delta 0,06) : 10 sur la consigne cachée surlignée, 10b sur « sAIfe l'a retenue » et les canaris C-7A3F/C-2B91, 10c sur les badges « Critique »/« Agent arrêté » et le titre. Les vraies captures (INC-0016) sont conservées, seulement présentées plus proprement.
- **Arrêt sur image.** Pivot du film, soigné à la demande de Guilhem : flash blanc d'une image, désaturation + teinte rouge très sombre en 0,4 s, légère secousse amortie, le montant « 41 760 € partis. » qui monte en punch sous le fantôme de l'écran. Tenu 3 s (court, comme demandé), pas de séparation RVB (réservée au rembobinage). Le centrage du montant est écrit en fonction du facteur d'échelle (et non de `(W-w)/2`) : avec un `scale` en eval=frame, `w` restait figé une image ou deux et le montant apparaissait décalé à droite puis sautait au centre (téléportation signalée par le fondateur). Corrigé dans `recettes.sh` (`arret_dramatique`).
- **Agents IA d'abord.** Le carton d'ouverture et le premier incident agent tiennent les 9 premières secondes.
- **Fraude = faux changement de RIB d'un fournisseur connu** (Atelier Nord, 41 760 €), pour que le geste retenu parte chez la finance (`/validation`) plutôt qu'au SOC.
- **Bug du rapport corrigé** : le film montre le rapport d'INC-0003 (coupé par le scénario, synthèse cohérente), pas celui d'INC-0002 dont la synthèse restait « aucun analyste n'a décidé ».

## Pour la v3 calée sur la voix de Paul

Changer les durées dans `plans_danger`, `plans_saife`, `plans_produit`, la liste `PLANS`, puis relancer `musique.py` avec les repères décalés. Les captures restent valables.
