# Démo du jury : déroulé court

Deux minutes dans le pitch de 5 minutes (Round 1), une minute vingt-cinq en finale. Orbis Pay et ses mails sont fictifs, l'agent est scripté, rien ne sort de 127.0.0.1. Le guide détaillé reste [DEMO.md](DEMO.md).

## Avant de monter sur scène (T-10 min)

1. `cd messagerie && ./demarrer.sh --service` : Mailpit sur 8716 et 8717, verdicts sur 8715. Taper sans valider `uv run python envoyer_demo.py --cas sosie`.
2. `cd app-mac && ./construire.sh --lancer` : le menu du bouclier doit afficher « Boîte de démo : N mails ».
3. Répétition complète : `./demo.sh jury`, puis « Couper l'agent » dans la console.
4. À la racine, taper sans valider `./demo.sh jury`. Grande police.
5. Console sur `http://localhost:5173`, zoom à 125 %, nom de l'analyste choisi en haut à droite (sans lui, « Appliquer » une règle attend sans rien dire). Le rapport s'ouvre depuis le dossier, « Exporter » puis « Rapport » : une adresse `/api/…/rapport` tapée dans un onglet, sur 8700 comme sur 5173, répond « Jeton absent ou invalide. ».
6. Ne pas lancer `./lancer.sh`. Mode Ne pas déranger, messageries fermées.

La pop-up Mac passe avant la commande : « Annuler » n'ouvre aucun incident, et `./demo.sh jury` repart ensuite d'une base vide.

## Déroulé

| t | Action | Ce qu'on dit |
|---|---|---|
| 0:00 | Entrée sur `envoyer_demo.py --cas sosie` | « Camille, à la comptabilité, reçoit un mail d'Orbis Pay. » |
| 0:03 | la pop-up s'ouvre | lire la première raison : « Elle est prévenue avant d'avoir cliqué, et on lui dit pourquoi. » |
| 0:14 | « Annuler », puis « Compris » sur le coach | « Trois lignes pour reconnaître le piège. Son poste n'est jamais bloqué. » |
| 0:25 | Entrée sur `./demo.sh jury` | « Passons à l'agent. On repart d'une base vide, devant vous. » |
| 0:35 | les scènes défilent, puis le chrono | « Un des mails de Jean cache une consigne. L'agent la suit et veut envoyer son rapport avec une image qui pointe dehors. La passerelle retient l'appel avant qu'il parte. » |
| 0:55 | clic sur le lien de l'incident agent imprimé par le script | |
| 1:00 | lire « Ce qui s'est passé » | « Chaque phrase renvoie à sa preuve dans la boîte noire. » |
| 1:10 | « Voir le mail en entier », puis Échap | « La consigne surlignée, les liens désarmés. » |
| 1:25 | montrer « Décision conseillée » | « sAIfe conseille de couper. Il n'applique rien seul. » |
| 1:35 | « Couper l'agent », motif en trois mots, Entrée, puis montrer le terminal après le bandeau de 5 s | « L'agent perd ses accès, aucun rapport n'est parti. » |
| 1:45 | « Exporter », puis « Rapport » : il s'ouvre dans un nouvel onglet | « Une page pour le RSSI, avec le sceau du journal. » |
| 2:00 | rendre la main | |

En finale : sauter « Voir le mail en entier » et le rapport.

## Gestes critiques : deux virements (30 s, après le déroulé)

sAIfe ne se montre que s'il y a un signal de risque. Un virement normal part sans rien afficher. Seul un signal ouvre la pop-up, sans que l'équipe sécurité voie le virement.

| Action | Ce qu'on voit, ce qu'on dit |
|---|---|
| `curl -X POST 127.0.0.1:8712/avertir -d '{"categorie":"mail_externe","geste":"virement","gravite":"critique","message":"Virement de 320 € à Imprimerie du Lys."}'` | rien ne s'affiche : « Fournisseur habituel, montant habituel : le virement part, sAIfe reste invisible. » |
| même commande avec `"message":"Virement de 3 480 € à Atelier Nord, nouveau RIB FR76 1111 2222 3333 4444 5555 0042."` | pop-up « Retenu » : « Ce RIB n'a jamais servi pour Atelier Nord. » « On demande au salarié de faire confirmer par son responsable, pas par la sécurité. » |

Les numéros d'incident changent avec l'ordre des scènes : le lien imprimé par le script fait foi. Les lignes « Préparation » (arrêt du backend, copie de la base, relance) ont pris moins de 2 s en répétition.

« Couper l'agent » demande un motif court, puis laisse 5 s pour annuler : la décision ne part qu'à la fin du bandeau. Changer d'onglet ou recharger pendant ces 5 s annule la coupure sans rien dire.

## Ajouts, seulement après trois répétitions sans accroc

- Désarmeur : `cd interne && uv run python -m orbis.demo --scenario jury --desarmeur --backend http://127.0.0.1:8700`. `./demo.sh jury` ne l'active pas.
- Preuve « vrai modèle, vrais accès » : `cd interne && uv run --extra reel python -m orbis.demo --scenario reel --essais 3`. Un vrai Haiku pilote l'agent sur de vrais services locaux (Mailpit, API bancaire, fichiers) ; sans sAIfe le mail d'exfiltration part vraiment, avec sAIfe il est retenu et coupé. Tout est isolé, le 8700 n'est pas touché. Détail et commandes : `docs/REEL_OU_SIMULE.md`.
- Geste critique après un mail frauduleux : `envoyer_demo.py --cas fraude_president`, puis « Continuer ». Le relecteur refuse en 7 s environ (il attend Haiku avant que les règles tranchent), l'incident arrive à la SOC : la liste ne montre ni montant ni bénéficiaire, le dossier s'ouvre en clair parce qu'il porte un signal de fraude, et cette consultation est notée au journal scellé. Boutons « Accorder » et « Refuser » dans la console.
- Incident salarié en direct : `envoyer_demo.py --cas lien_menteur`, puis « Continuer ».

## Si ça casse

| Panne | Réaction |
|---|---|
| pas de pop-up après 5 s | `curl -X POST 127.0.0.1:8712/avertir -d '{"categorie":"phishing","message":"Ce mail est sûrement frauduleux."}'` |
| app Mac morte | captures `app-mac/captures/mail.png` et `mail-coach.png` |
| `./demo.sh jury` s'arrête | lire l'erreur ; port occupé : `./demo.sh jury --arreter`, puis relancer ; « appel sortant … pas retenu » : une règle du SOC bloque l'envoi, la retirer ou relancer sans `--garder-base` ; au-delà de 20 s, passer la vidéo |
| console figée | recharger ; sinon le chrono du terminal et le rapport |
| réseau coupé | rien à changer : agent scripté, aucun modèle appelé. Ne pas montrer le relecteur IA sans l'avoir répété Wi-Fi coupé |

Une personne au clavier, l'autre parle.
