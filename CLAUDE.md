# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Le projet

sAIfe, hackathon Secure Horizons (ESSEC, 10-11 octobre 2026). Le code garde le nom de travail `dedale` (dépôt, dossiers, modules, variables `DEDALE_*`, `Dedale.app`) : ne pas le renommer. Le produit pose des pièges que seul un agent IA suit, attrape les gestes risqués des salariés sur leur poste, reconstruit la chaîne dans une boîte noire pour le SOC et laisse un humain valider chaque riposte forte. L'entreprise protégée, Orbis Pay (`orbispay.example`), est fictive. Le dépôt ne contient aucune donnée réelle, aucun secret réel, et rien ne doit viser un système réel.

Tout est en français : identifiants, commentaires, docstrings, messages de commit, documentation. Garder cette langue, accents compris, dans le code ajouté.

`CONTRATS.md` fait foi entre les modules (schéma d'événement, endpoints, types d'incident, conventions). Le lire avant de toucher à une interface entre deux modules. Un changement de contrat s'ajoute en bas du fichier, sans casser l'existant. Chaque module avait un « agent » propriétaire (A à E) : la règle d'origine veut qu'un agent ne modifie que son dossier et sa ligne du `README.md`.

## Commandes

Python 3.12+ géré par `uv`, un `pyproject.toml` par module. Le nom de l'extra de test diffère selon le module :

```bash
# backend, interne, attaque, poste : pytest est dans l'extra optionnel « dev »
cd backend && uv run --extra dev pytest
cd backend && uv run --extra dev pytest tests/test_humain.py::test_source_humain_et_surface_poste_acceptees

# leurres : pytest est dans un dependency-group, inclus d'office
cd leurres && uv run pytest

# console (Vite + React + TS)
cd console && npm run dev            # http://localhost:5173, proxy /api et /ws vers 8700
cd console && npx tsc --noEmit       # vérification des types
cd console && npm run build          # tsc puis vite build dans console/dist/

# règles Sigma
uvx --from sigma-cli sigma check sigma/
```

Pas de linter configuré, ni en Python ni côté console.

Lancement et démos :

```bash
./lancer.sh [--seed]                                   # backend 8700, leurres 8701/8711, console 5173 ; --seed charge une démo
cd backend && uv run uvicorn app.main:app --port 8700  # backend seul
cd leurres && uv run python lancer.py                  # surface HTTP 8701 + MCP 8711, un seul process
cd interne && uv run python -m orbis.demo [--backend-reel] [--cerveau scripte|cli|api|auto]
cd poste && uv run python -m garde.simulateur [--sans-reseau] [--choix mix|continuer|annuler]
cd attaque && uv run python campagne.py [--mode auto|autonome|surface] [--graine N]
```

## Architecture

Un seul moteur traite trois sources. Chaque module émet des événements vers le backend, qui classe, ouvre les incidents, reconstruit la chaîne et attend la décision de l'analyste.

- `leurres/` : surface exposée d'Orbis Pay (site, API, doc, serveur MCP leurre, labyrinthe). Source `externe`, leurres `L-xxxx`.
- `interne/` : agent IA interne d'Orbis Pay et passerelle « boîte noire ». Source `interne`, canaris `C-xxxx`. C'est une bibliothèque : le port 8702 réservé n'est servi par rien, le banc l'appelle en direct (`orbis.agent.AgentInterne`).
- `poste/` : garde du corps du poste du salarié. Source `humain`, surface `poste`, événement `avertissement` portant le choix `continuer`/`annuler`.
- `attaque/` : banc de mesure. Génère un trafic dont il connaît la nature (bibliothèque standard seule, aucune dépendance).
- `backend/` (FastAPI, 8700) : collecteur, tri, incidents, boîte noire, brouillon NIS2, exports ECS/Sigma, mesures, flux WS. Sert aussi `console/dist` une fois construit.
- `console/` : écrans de l'analyste. `sigma/` : règles génériques rejouables dans un SIEM. `landing/` : page statique.

### Flux d'un événement

1. Un module envoie `POST /api/evenements`. `backend/app/store.py` (`Store.ingerer`) classe la session en mémoire de façon synchrone (`classement.py` : signaux pondérés, seuils `DEDALE_SEUIL_AGENT_IA`/`DEDALE_SEUIL_SCRIPT`), ouvre ou met à jour l'incident et renvoie une `consigne` en moins de 50 ms.
2. La persistance SQLite et la diffusion WS passent par une file asyncio que vide un unique écrivain (`main.py`, `_ecrivain`). Un arrêt normal vide cette file ; une interruption brutale peut perdre un élément encore en attente. Un échec de persistance ne remonte pas à l'appelant, mais l'état de santé signale la dégradation.
3. Le module applique la consigne : `labyrinthe`, `contre_injection` ou `bloquer` côté `leurres/` ; `suspendre` côté `interne/`, dont la passerelle retient l'appel d'outil et interroge `GET /api/sessions/{id}` chaque seconde jusqu'à `active` ou `coupee`. Pour `humain`/`physique`, la consigne vaut toujours `aucune` : le poste n'est jamais bloqué.
4. L'analyste décide par `POST /api/incidents/{id}/decision`. Pour un agent, `couper` et `valider_riposte` passent la session en `coupee`, `reprendre` et `ignorer` en `active`. Pour un incident `humain_*`, seules `clore` et `ignorer` sont valides et ne changent pas l'état du poste.

Un module ne doit jamais tomber si le backend est absent : chaque client (`leurres/orbis/backend.py`, `poste/garde/backend.py`, la passerelle interne) avale l'erreur et continue sans consigne.

L'état en mémoire du `Store` fait autorité pour les lectures de l'API. SQLite (`data/dedale.db`, ignoré par git) conserve les faits et sert à reconstruire cet état au démarrage. Les anciennes bases, créées avant le rechargement, peuvent contenir un journal partiel ; conserver leur contenu et vérifier la migration avant une démo.

### Neutralisation du texte piégé

Tout texte venu d'un leurre, d'un canari, d'une description d'outil MCP ou d'une pop-up du poste passe par `backend/app/securite.py` (`neutraliser`, `neutraliser_details`) avant stockage : préfixe `[leurre, neutralisé]`, HTML échappé, longueur bornée. La console, le SIEM et les prompts envoyés au modèle (`llm.py`) ne reçoivent que cette forme inerte. Un nouveau champ de `details` susceptible de porter du texte piégé doit suivre le même chemin. `poste/` neutralise déjà ses preuves de son côté (préfixe `[preuve, neutralisée]`, un secret ne laisse fuir que sa catégorie et sa longueur).

### Types d'incident et boîte noire

`incident.type` vaut `interne_canari`, `interne_outil_mcp`, `interne_droits`, `interne_inter_agent`, `interne_appel`, `interne_chatbot`, `interne_memoire`, ou l'un des cinq `humain_*` (`secret`, `mail_externe`, `upload_ia`, `phishing`, `intrusion_physique`). Le type et le titre se décident dans `Store._type_titre`. La chaîne vient de `incidents.py` : `construire_chaine` (phases `entree|consigne|outil|sortie|riposte`) pour un agent IA, `construire_chaine_humaine` (phases `contexte|action_risquee|avertissement|choix|consequence`) pour un geste humain.

Ajouter un type d'incident touche au moins `store.py`, `incidents.py`, le mapping de la console (`console/src/ui/primitives.tsx`, `TYPE_INCIDENT` et `PILIERS`) et une section de `CONTRATS.md`. La console tolère un type ou un champ inconnu et retombe sur un libellé générique.

### Vérité terrain et mesures

Le banc préfixe ses sessions `banc-<verite>-NNNN` (`humain|script|agentia|interne`) et pose en secours `details.verite_terrain`. `backend/app/mesures.py` en tire `taux_detection` et `faux_positifs`. Les sessions sans ce préfixe (démo interne, poste) n'entrent pas dans ces deux taux. Côté `leurres/`, la session suit le cookie `dedale_sid` : le banc doit l'envoyer en plus de l'en-tête `X-Dedale-Session`, sinon le préfixe se perd et les mesures tombent à zéro.

### Modèles

`DEDALE_MODELE_AGENT` (défaut `claude-sonnet-5-5`) et `DEDALE_MODELE_LEGER` (défaut `claude-haiku-5-5`), clé `ANTHROPIC_API_KEY` dans `.env` (voir `.env.example`). Sans clé, l'agent interne peut passer par `claude -p`. `DEDALE_CERVEAU` force le cerveau de l'agent interne (`interne/orbis/cerveau.py`) : `CerveauScripte` déterministe, tempérament `prudent` ou `naif`, pour les tests et la démo reproductible. La démo commune utilise ce cerveau scripté. Le brouillon NIS2 du backend est déterministe, sans appel modèle.

## Tests

Aucune suite n'a besoin d'un service lancé ni du réseau.

- `backend/tests/conftest.py` pointe `DEDALE_DB` vers une base temporaire et pose `DEDALE_LLM=off` avant d'importer l'app, puis vide le `Store` singleton entre chaque test. Un nouvel attribut d'état dans `Store` doit aussi être remis à zéro dans la fixture `_reset_store`.
- `interne/` démarre un faux backend HTTP en mémoire (`orbis/backend_simule.py`).
- `leurres/` remplace le client backend par un `BackendFaux` (monkeypatch) et met l'attente du labyrinthe à zéro.

## Console sans backend

Tant que `/api/mesures` ne répond pas, la console tourne sur `src/api/mock.ts`, calqué sur `CONTRATS.md`, et sonde le backend toutes les 5 s pour basculer en direct. Une forme renvoyée par le backend qui change doit aussi changer dans le mock, sinon les deux divergent sans bruit.
