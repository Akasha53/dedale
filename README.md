# Dédale

[![Scan de secrets : 0 alerte](https://img.shields.io/badge/scan%20de%20secrets-0%20alerte-brightgreen)](docs/SCAN_SECRETS.md)

Projet du hackathon Secure Horizons (ESSEC, 10-11 octobre 2026), Track 2. L'entreprise, les mails, les secrets et les paiements sont fictifs (Orbis Pay), et tout tourne en local.

## Le problème

Deux maillons faibles se côtoient dans une entreprise. Un salarié peut suivre un lien trompeur ou coller une clé dans un chatbot. Son assistant IA peut obéir à une instruction cachée dans un mail et envoyer des données à l'extérieur. Les outils de sécurité les traitent séparément, avec deux journaux et deux consoles.

Dédale les met dans une même console SOC. Le garde du poste prévient le salarié avant le geste risqué. La passerelle retient l'appel suspect d'un agent. Une boîte noire garde les événements et les décisions, et chaque incident peut être exporté.

## Architecture

| Module | Rôle | Port |
|---|---|---|
| `backend/` | API de la console (FastAPI) : collecteur d'événements, tri humain / script / agent IA, incidents, boîte noire, brouillon NIS2, exports ECS et Sigma, mesures, flux WebSocket | 8700 |
| `console/` | Console web du SOC (Vite, React, TypeScript) : temps réel, incidents, leurres, mesures. Servie en dev par Vite | 5173 |
| `poste/` | Garde du poste : simulateur de gestes salariés (secret collé, mail externe, dépôt vers une IA, phishing). Il avertit, laisse choisir `continuer` ou `annuler`, puis informe le backend | aucun |
| `interne/` | Agent IA interne d'Orbis Pay (mails et documents synthétiques, outils natifs et MCP) et passerelle qui journalise, détecte l'exfiltration et les canaris, puis retient l'appel en attendant l'analyste | aucun |
| `leurres/` | Surface exposée d'Orbis Pay : site, API et documentation fictifs, plus un serveur MCP leurre. 15 leurres invisibles pour un humain, visibles pour un lecteur automatique | 8701, 8711 |
| `attaque/` | Banc d'attaque et de mesure : trafic étiqueté (humain, script, agent IA, agent interne détourné) contre la surface fictive | aucun |
| `app-mac/` | Application de barre de menus (Swift) qui affiche l'avertissement du poste | 8712 |
| `sigma/` | Règles Sigma (IA et humain) utilisées par les exports | |
| `landing/` | Page de présentation statique | |

Les formats d'échange entre modules sont décrits dans [CONTRATS.md](CONTRATS.md).

## Installation

Il faut Python 3.12 ou plus, `uv`, Node.js, npm et `curl`. L'app Mac demande en plus macOS 13 et Swift 5.9. Depuis un clone neuf :

```bash
cd console && npm ci && cd ..
cd backend && uv sync && cd ..
cd leurres && uv sync && cd ..
cd interne && uv sync && cd ..
```

Sans clé, l'agent interne reste sur son cerveau scripté. `.env.example` liste les variables facultatives.

## Lancement

```bash
./lancer.sh            # backend, leurres et console (ajouter --seed pour des données de démo)
./demo.sh              # dans un second terminal : scène salarié puis scène agent
```

Ouvrir `http://localhost:5173`. `lancer.sh` refuse de démarrer si un des ports 8700, 8701, 8711 ou 5173 est déjà pris. Le déroulé des scènes et leurs résultats attendus sont dans [docs/DEMO.md](docs/DEMO.md).

Autres commandes :

```bash
cd poste && uv run python -m garde.simulateur     # gestes salariés, sans la démo complète
cd attaque && uv run python campagne.py           # banc d'attaque
cd app-mac && ./construire.sh --lancer            # app Mac (voir app-mac/README.md)
```

## Tests

132 tests pytest (backend 45, interne 35, leurres 19, poste 17, attaque 16) et 22 tests unittest sur le script de démo, soit 154 au 10 octobre 2026.

```bash
cd backend && uv run --extra dev pytest
cd ../interne && uv run --extra dev pytest
cd ../poste && uv run --extra dev pytest
cd ../leurres && uv run pytest
cd ../attaque && uv run --extra dev pytest
cd ../console && npm run build        # vérification des types et build
cd .. && python3 -m unittest discover -s scripts/tests
```

## Secrets

Aucun secret réel dans le dépôt ni dans son historique. Les clés qui apparaissent (canaris, fixtures de tests) sont des valeurs fictives d'Orbis Pay. Le contrôle combine gitleaks et un script Python, et tourne avant chaque commit :

```bash
git config core.hooksPath .githooks      # une fois par clone
python3 scripts/scan_secrets.py          # arbre et historique
gitleaks git . --config .gitleaks.toml   # si gitleaks est installé
```

Résultats, périmètre et valeurs fictives autorisées : [docs/SCAN_SECRETS.md](docs/SCAN_SECRETS.md). Le badge en tête de page est à retirer si ce scan cesse de passer.

## Limites connues

- Scénarios et données fictifs. Les noms, les mails, les secrets et les paiements d'Orbis Pay ont été écrits pour la démo.
- Le trafic du banc est synthétique. Ses taux de détection ne prédisent pas une performance en production.
- Pas d'intégration native : le poste simule les gestes, il ne surveille ni le presse-papiers, ni le navigateur, ni la messagerie. Pas de connexion à Outlook, Gmail ou Claude Code.
- Les décisions ne coupent pas le poste d'un salarié. Pour un agent, « couper » arrête la session et révoque son jeton ; l'envoi d'un rapport reste local.
- Le texte NIS2 est un brouillon à relire. Aucune validation réglementaire, aucun envoi automatique. Les correspondances OWASP et ATLAS restent à confirmer ([leurres/NOTES-mapping.md](leurres/NOTES-mapping.md)).
- L'app Mac s'appuie sur une signature ad hoc et n'est pas notarisée. Son port 8712 n'a pas d'authentification : un programme local peut y afficher une fausse alerte.
- La démo commune emploie un cerveau scripté pour rester reproductible. Les appels, chatbots, délégations entre agents et mémoire persistante sont un chantier interrompu.

## Documents

[Guide de démonstration](docs/DEMO.md), [fiche jury](docs/FICHE_JURY.md), [plan du 10 octobre](docs/PLAN_NILA_2026-10-10.md), README de chaque module.
