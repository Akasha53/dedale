# Répétition générale de la démo (11 octobre 2026)

Tout a été joué sur un environnement à part, sans toucher au 8700, à la Mailpit de démo (8716, 8717), à la pop-up de l'app Mac (8712) ni à `data/journaux/services.json` :

- backend sur 8794, `DEDALE_DB` et `DEDALE_JETONS` dans un dossier temporaire ;
- console Vite sur 5294 (`vite --port 5294`, `DEDALE_BACKEND=http://127.0.0.1:8794`) ;
- `./demo.sh jury` joué par un petit lanceur qui appelle `scripts/demo_jury.py` avec ses journaux dans le dossier temporaire ;
- Chrome sans fenêtre, profil temporaire, `--use-mock-keychain --password-store=basic`, piloté par CDP pour cliquer dans la console.

Les durées sont celles de cette machine, un MacBook qui faisait tourner en même temps la démo de Guilhem.

## Résultat par étape

| # | Étape | Résultat | Durée |
|---|---|---|---|
| 1a | `./demo.sh jury` (base neuve), puis « Couper l'agent » dans la console | OK | 1,9 s jusqu'à « Décidez dans la console », 6,4 s du clic à la décision |
| 1b | `orbis.demo --scenario jury --desarmeur` | OK | moins de 1 s |
| 1c | `orbis.demo --scenario jury` (sans désarmeur, couper puis reprendre) | OK | 4,0 s |

## Détail

### 1. Démo du jury

1a. `jury_isole.py --backend http://127.0.0.1:8794 --console http://localhost:5294 --attente 120`, sans `--garder-base`, donc par le chemin du jour J : arrêt du backend, copie de la base, relance.

- Préparation complète en moins de 2 s : backend arrêté, base copiée dans `sauvegardes/` (0 événement), backend relancé, santé ok, flux `/ws` branché. La ligne de `DEMO_JURY.md` qui disait cette durée « à mesurer » est corrigée. Sur le 8700, la copie d'une grosse base peut allonger un peu.
- Scène salariée : pop-up à +0,1 ms, INC-0001 `humain_phishing` dans le flux de la console à +6,9 ms.
- Scène agent : appel `envoyer_rapport` retenu à +31 ms (canaris C-7A3F et C-2B91), INC-0002 `interne_canari` dans la console à +37 ms.
- Console (Chrome sans fenêtre) : le dossier INC-0002 s'affiche en 0,4 à 0,9 s avec « Ce qui s'est passé », « Décision conseillée », « Voir le mail en entier » et le bouton « Couper l'agent » marqué « conseillé ».
- Clic sur « Couper l'agent » : un champ « En quelques mots, pourquoi » s'ouvre (motif obligatoire sur un incident grave), puis un bandeau « Annuler » de 5 s. La décision n'arrive au backend qu'au bout de ces 5 s : 6,4 s entre le premier clic et la décision. Le terminal affiche ensuite « Décision reçue … Couper. Agent arrêté, jeton révoqué, aucun rapport envoyé. » et sort avec le code 0.
- Piège rencontré : fermer l'onglet pendant les 5 s annule la décision sans bruit. Au premier essai, rien n'est parti. Sur scène, ne pas changer d'onglet avant la fin du bandeau.

1b. `uv run python -m orbis.demo --scenario jury --desarmeur --backend http://127.0.0.1:8794` : un passage retiré en 1,2 ms avant lecture, l'agent ne demande jamais le coffre, rapport envoyé à Jean, INC-0003 `interne_desarme`. Code 0.

1c. Même commande sans `--desarmeur` : issue « couper » (coffre lu 0 fois, jeton révoqué, relance refusée, INC-0004) puis « reprendre » (coffre lu une fois sur décision, envoi suivant retenu puis coupé, INC-0005). Détection en 0,05 ms, décision scriptée après 1,25 s. Code 0.
