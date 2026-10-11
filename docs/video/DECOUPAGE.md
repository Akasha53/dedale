# Vidéo de démo v1 : découpage

Fichier : `~/Downloads/sAIfe-demo-v1.mp4`, 2 min 15 s, 1920 × 1080, 30 i/s, H.264 et AAC. Sans voix, textes en français. Refaire : `bash docs/video/montage-v1.sh` (voir l'en-tête du script). Les captures viennent d'un backend isolé (port 8790, base temporaire), jamais du 8700.

Orbis Pay, Atelier Nord, Michèle Delaconta et Claire Dubois sont fictifs. Le prénom de Michèle n'apparaît que sur le premier carton. À l'écran, la salariée n'a pas de nom : le mail est adressé à `compta@orbispay.example`, l'espace de validation affiche « poste hors annuaire », la console du SOC « Salarié 7751 ».

Le scénario suit le guide (`docs/GUIDE_VIDEO.md`), avec un changement : la fraude est un faux changement de RIB d'un fournisseur connu (Atelier Nord, 41 760 €), pas une fraude au président. Un geste retenu sans signal de fraude part chez la finance (`/validation`) ; une fraude au président ouvre un incident au SOC et n'aurait pas montré la finance qui tranche.

## Plans

| N° | Temps | Image | Mouvement | Texte à l'écran | Source |
|---|---|---|---|---|---|
| 1 | 0:00,0 à 0:04,5 | carton blanc | fondu, montée de 14 px | « Michèle Delaconta » / « Comptable chez Orbis Pay » / « Personnage et entreprise fictifs. » | `carton.swift` |
| 2 | 0:04,5 à 0:09,0 | messagerie : boîte, notification, mail d'Atelier Nord ouvert | fondus enchaînés, poussée 1 → 1,06 | « Un mail d'un fournisseur habituel. » | `capture/scene.html` (maquette de messagerie) |
| 3 | 0:09,0 à 0:13,5 | même mail | zoom 1 → 1,7 sur le bloc RIB en 3 s | « Il change de RIB. » | idem |
| 4 | 0:13,5 à 0:18,0 | banque fictive : IBAN puis montant tapés | aucun | « Elle prépare le virement. » | `capture/scene.html` (banque) |
| 5 | 0:18,0 à 0:22,5 | survol du bouton, clic à 0:21,0, « Virement envoyé » | anneau de clic | « Elle l'envoie. » | idem |
| 6 | 0:22,5 à 0:28,5 | arrêt sur image, voile blanc | carton à 0:23,0 | « 41 760 € » (rouge) / « partis sur le compte d'un escroc. » | `recettes.sh`, `arret_sur_image` |
| 7 | 0:28,5 à 0:33,0 | plans 1 à 5 à l'envers, jusqu'au blanc du début | rembobinage accéléré, bande de bruit, ◀◀ | aucun | `recettes.sh`, `rembobine` |
| 8 | 0:33,0 à 0:37,5 | carton blanc | fondu | « Stop. » / « Maintenant, avec sAIfe. » | `carton.swift` |
| 9 | 0:37,5 à 0:42,0 | même mail, même saisie, en plus rapide | aucun | « Même mail, même virement. » | `capture/scene.html` |
| 10 | 0:42,0 à 0:46,5 | clic à 0:43,2 ; pop-up sAIfe « vérifie ce virement… » puis « Retenu » | anneau de clic | « Cette fois, sAIfe le retient. » | pop-up reproduite en HTML d'après `FenetreAlerte.swift`, `QuatreYeux.swift`, `Theme.swift` ; motif rendu par le vrai `POST /api/relecteur/verifier` |
| 11 | 0:46,5 à 0:51,0 | la pop-up « Retenu » | zoom 1 → 1,9 en 3 s | « Elle sait pourquoi. » | idem |
| 12 | 0:51,0 à 0:55,5 | espace `/validation`, fiche du virement de 41 760 € | zoom 1 → 1,35 | « La finance reçoit la demande. » | console réelle, `capture/capture-validation.js` |
| 13 | 0:55,5 à 1:00,0 | motif tapé, signé « Claire Dubois », Finance, « Refuser », puis « Refusé par Claire Dubois (finance) » | zoom fixe 1,55 | « Elle appelle Atelier Nord et refuse. » | idem, décision réelle (`POST /api/validation/gestes/{id}/decision`) |
| 14 | 1:00,0 à 1:04,5 | carton blanc | fondu | « 41 760 € » (vert) / « restés chez Orbis Pay. » | `carton.swift` |
| 15 | 1:04,5 à 1:09,0 | console : incident « Agent IA détourné par une instruction cachée » | zoom 1 → 1,25 | « Un agent IA lit un mail piégé. » | console réelle, `./demo.sh jury` sur le backend isolé |
| 16 | 1:09,0 à 1:13,5 | « Voir le mail en entier » : la consigne surlignée | zoom 1 → 1,3 | « La consigne cachée, surlignée. » | idem |
| 17 | 1:13,5 à 1:18,0 | pré-tri du relecteur, motif de coupure, « Agent arrêté, rien n'est sorti » | zoom fixe 1,35 | « L'analyste coupe l'agent. » | idem, décision réelle |
| 18 | 1:18,0 à 1:21,0 | « Aucun agent ne fait de virement de plus de 10 000 €. » tapé | zoom fixe 1,4 | « Une règle, écrite en français. » | console réelle, écran des règles |
| 19 | 1:21,0 à 1:25,5 | agent des règles (Haiku) : session ouverte, « session fermée · jeton révoqué · 1 appel en 4,5 s », « Règle n°2 active » | idem | « Un agent la prépare et se ferme. » | idem, vrai appel `claude -p` |
| 20 | 1:25,5 à 1:30,0 | « Retire les droits en trop aux agents », droits qui partiront, « 11 droits retirés à 3 agents » | zoom fixe 1,15 | « Les droits en trop partent en un clic. » | idem |
| 21 | 1:30,0 à 1:34,5 | « Tentative bloquée : ouvrir le coffre, droit retiré par la règle n°3 », puis le fil « Refusée » | zoom fixe 1,2 | « L'agent retente d'ouvrir le coffre : refusé. » | `orbis.demo --scenario jury` rejoué après le retrait |
| 22 | 1:34,5 à 1:37,5 | page d'avertissement de l'extension Chrome, site sosie d'Orbis Pay | poussée 1 → 1,08 | « Il prévient aussi sur les sites sosies. » | `extension/avertissement.html`, rendu avec une réponse simulée du service worker |
| 23 | 1:37,5 à 1:40,5 | pop-up de l'app Mac, « Facture-octobre.pdf.app » mis de côté | poussée 1 → 1,08 | « Et met de côté les fichiers piégés. » | `captures/saife/app-telechargement.png` |
| 24 | 1:40,5 à 1:45,0 | incident d'outil MCP inconnu, pastille « Journal intact » | zoom 1 → 1,25 en 3 s | « Chaque décision est scellée. » | console réelle, `orbis.demo --scenario outil-inconnu` |
| 25 | 1:45,0 à 1:49,5 | rapport d'une page, encadré « Journal intact » et sceau SHA-256 | zoom 1 → 1,3 | « Une page pour le RSSI. » | `GET /api/incidents/INC-0003/rapport` |
| 26 | 1:49,5 à 1:55,5 | menu « Exporter », puis extraits ECS 8.11 et Sigma | zoom 1,2 → 1,35, puis poussée | « Exports ECS, Sigma et CEF pour le SIEM. » | console réelle ; page de mise en forme des exports réels d'INC-0003 |
| 27 | 1:55,5 à 2:00,0 | « Salariés en direct » : « Salarié 7751 · Finance » | zoom 1 → 1,3 | « La sécurité voit un pseudonyme, pas un nom. » | console réelle |
| 28 | 2:00,0 à 2:06,0 | « Ce que sAIfe regarde sur ce poste » | poussée 1 → 1,12 | « Le salarié voit ce que sAIfe lit. » | `captures/saife/app-transparence.png` |
| 29 | 2:06,0 à 2:15,0 | logo et logotype | fondus au blanc | « sAIfe » / « Salariés prévenus. Agents IA retenus. » | `console/src/assets/dedale.svg` (nouveau logo) |

## Musique

`musique.py --acte2-fin 64.5 --montage-fin 70.5 --logo 126 --finance 999 --duree 140`, puis `mixer` (-16 LUFS). Silence de 0:22,5 à 0:25,5 sur l'arrêt sur image, montée pendant le rembobinage, choc à 0:33,0 sur « Stop. », acte 2 en majeur jusqu'au carton vert, accord final sur le logo.

## Refaire les captures

Tout tourne en headless (Chromium de Playwright, profil jetable, 1600 × 900 à l'échelle 2), sans fenêtre ni autorisation macOS. Les scripts sont dans `docs/video/capture/` et écrivent dans `/tmp/saife-video-v1/rec/`.

1. Backend isolé : `DEDALE_DB`, `DEDALE_JETONS` et `DEDALE_CONFIG` dans un dossier jetable, `uvicorn app.main:app --port 8790` ; console : `DEDALE_BACKEND=http://127.0.0.1:8790 DEDALE_JETONS=… vite --port 5190`.
2. Données : `./demo.sh jury --backend http://127.0.0.1:8790 --console http://localhost:5190 --garder-base --sans-decision`, `orbis.demo --scenario outil-inconnu`, puis le virement par `POST /api/relecteur/verifier` avec le jeton du poste (Atelier Nord, 41 760 €, nouveau RIB).
3. `node capture-scene.js`, `node capture-extension.js`, `node capture-validation.js`, puis `console-seqA.js` et `console-seqA2.js` (incident, coupure), `console-seqB.js b « Aucun agent ne fait de virement de plus de 10 000 €. »` et `console-seqB.js c « Retire les droits en trop aux agents »`, `orbis.demo --scenario jury` rejoué, puis `console-cap.js` pour la tentative bloquée, `console-seqD.js`, `console-seqE.js`, `console-seqF.js`. `console-capfile.js` photographie une page locale (rapport, extraits ECS et Sigma).

## Pour la v2 calée sur la voix de Paul

Changer les durées dans `plans_histoire` et `plans_console`, la liste `PLANS`, puis relancer `musique.py` avec les nouveaux repères. Les captures restent valables tant que le produit ne change pas d'écran.

## Absent de la v1

- L'app Mac native n'est pas filmée : la pop-up du virement est une reproduction HTML fidèle au code Swift, les autres écrans de l'app sont des captures de `captures/saife/`.
- La pop-up de l'app sur un mail douteux, les mesures du banc, la landing et l'écran partagé avant/après du guide ne sont pas dans cette version.
