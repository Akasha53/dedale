# Démo du jury : déroulé court

Deux minutes dans le pitch de 5 minutes (Round 1), une minute vingt-cinq en finale. Orbis Pay et ses mails sont fictifs, l'agent est scripté, rien ne sort de 127.0.0.1. Le guide détaillé reste [DEMO.md](DEMO.md).

## Avant de monter sur scène (T-10 min)

1. `cd messagerie && ./demarrer.sh --service` : Mailpit sur 8716 et 8717, verdicts sur 8715. Taper sans valider `uv run python envoyer_demo.py --cas sosie`.
2. `cd app-mac && ./construire.sh --lancer` : le menu du bouclier doit afficher « Boîte de démo : N mails ».
3. Répétition complète : `./demo.sh jury`, puis « Couper l'agent » dans la console.
4. À la racine, taper sans valider `./demo.sh jury`. Grande police.
5. Console sur `http://localhost:5173`, zoom à 125 %. Second onglet prêt : `http://127.0.0.1:8700/api/incidents/INC-000/rapport`.
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
| 1:25 | montrer « Décision conseillée » | « Dédale conseille de couper. Il n'applique rien seul. » |
| 1:35 | « Couper l'agent », puis montrer le terminal | « L'agent perd ses accès, aucun rapport n'est parti. » |
| 1:45 | second onglet : compléter le numéro, Entrée | « Une page pour le RSSI, avec le sceau du journal. » |
| 2:00 | rendre la main | |

En finale : sauter « Voir le mail en entier » et le rapport.

## Gestes critiques : deux virements (30 s, après le déroulé)

Dédale ne se montre que s'il y a un signal de risque. Un virement normal part sans rien afficher. Seul un signal ouvre la pop-up, sans que l'équipe sécurité voie le virement.

| Action | Ce qu'on voit, ce qu'on dit |
|---|---|
| `curl -X POST 127.0.0.1:8712/avertir -d '{"categorie":"mail_externe","geste":"virement","gravite":"critique","message":"Virement de 320 € à Imprimerie du Lys."}'` | rien ne s'affiche : « Fournisseur habituel, montant habituel : le virement part, Dédale reste invisible. » |
| même commande avec `"message":"Virement de 3 480 € à Atelier Nord, nouveau RIB FR76 1111 2222 3333 4444 5555 0042."` | pop-up « Retenu » : « Ce RIB n'a jamais servi pour Atelier Nord. » « On demande au salarié de faire confirmer par son responsable, pas par la sécurité. » |

Les numéros d'incident changent avec l'ordre des scènes : le lien imprimé par le script fait foi. La durée du redémarrage du backend (lignes « Préparation ») reste à mesurer en répétition ; parler pendant.

## Ajouts, seulement après trois répétitions sans accroc

- Désarmeur : `cd interne && uv run python -m orbis.demo --scenario jury --desarmeur --backend http://127.0.0.1:8700`. `./demo.sh jury` ne l'active pas.
- Geste critique après un mail frauduleux : `envoyer_demo.py --cas fraude_president`, puis « Continuer ». Le relecteur refuse, l'incident arrive à la SOC (montant en tranche, bénéficiaire masqué), boutons « Accorder » et « Refuser » dans la console.
- Incident salarié en direct : `envoyer_demo.py --cas lien_menteur`, puis « Continuer ».

## Si ça casse

| Panne | Réaction |
|---|---|
| pas de pop-up après 5 s | `curl -X POST 127.0.0.1:8712/avertir -d '{"categorie":"phishing","message":"Ce mail est sûrement frauduleux."}'` |
| app Mac morte | captures `app-mac/captures/mail.png` et `mail-coach.png` |
| `./demo.sh jury` s'arrête | lire l'erreur ; port occupé : `./demo.sh jury --arreter`, puis relancer ; au-delà de 20 s, passer la vidéo |
| console figée | recharger ; sinon le chrono du terminal et le rapport |
| réseau coupé | rien à changer : agent scripté, aucun modèle appelé. Ne pas montrer le relecteur IA sans l'avoir répété Wi-Fi coupé |

Une personne au clavier, l'autre parle.
