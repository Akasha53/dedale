# Tâche pour Paul : isoler les campagnes du banc de mesure

Le banc `attaque/` produit un trafic étiqueté, mais deux défauts empêchent d'utiliser son rapport comme mesure d'une campagne précise : les IDs `banc-<type>-NNNN` sont réutilisés à chaque exécution, et le client attend une liste sur `GET /api/sessions` alors que l'API renvoie `{ "sessions": [...] }`. Les chiffres de `GET /api/mesures` portent sur tout l'état du backend. Ils peuvent donc inclure des exécutions précédentes.

Cette tâche est indépendante de la démo salarié/agent. Elle peut partir de `main` et rester limitée à `attaque/` et sa documentation.

Travail attendu :

- Donner à chaque campagne un identifiant distinct, affiché et enregistré dans les sorties. Garder une graine fixe pour rendre le trafic reproductible, sans réutiliser les mêmes IDs de session entre deux campagnes. Une option permettant de fixer l'identifiant dans les tests serait utile.
- Lire la réponse réelle de `GET /api/sessions`, tout en acceptant l'ancien format liste si nécessaire.
- Calculer un bilan sur les seules sessions émises par la campagne courante : nombre observé, classes attendues et obtenues, faux positifs, faux négatifs et sessions non classées. Préciser les dénominateurs. Ne pas transformer une session absente ou `inconnu` en résultat favorable.
- Présenter les valeurs de `GET /api/mesures` comme des valeurs globales du backend. Si le backend est absent, afficher « non mesuré » au lieu de zéro.
- Ajouter des tests couvrant deux campagnes successives sur un même backend simulé, le format `{ "sessions": [...] }`, une session absente et une session non classée. Documenter une commande de campagne reproductible et la lecture du rapport.

Critères de validation : `cd attaque && uv run --extra dev pytest` passe ; le JSON et le résumé texte portent l'identifiant de campagne et les dénominateurs ; deux exécutions ne mélangent pas leurs sessions. Ne modifie pas `backend/`, `console/`, `interne/`, `poste/`, `landing/` ni `scripts/`. Aucun taux de détection en production ne doit être déduit du trafic synthétique.

Pour contribuer : ouvre une branche depuis `main`, puis une PR qui décrit le format du nouveau rapport et les tests lancés. Le contrat des événements est dans [`CONTRATS.md`](../CONTRATS.md) ; les commandes générales sont dans [`CLAUDE.md`](../CLAUDE.md).

## État au 10 octobre au soir

Les points ci-dessus sont faits dans `attaque/`, sans branche, directement sur `main`.

- Chaque exécution reçoit un identifiant de campagne, neuf par défaut ou fixé par `--campagne`. Les sessions s'appellent `banc-<type>-<campagne>-NNNN` : le backend lit toujours la vérité terrain au deuxième morceau, et la graine fixe rejoue le même trafic sous de nouveaux identifiants.
- `GET /api/sessions` est lu au format `{"sessions": [...]}`, l'ancien format liste reste accepté. `GET /api/incidents` et `GET /api/sessions/{id}` servent au bilan.
- Le bilan ne porte que sur les sessions émises par la campagne. Le dénominateur d'un taux est le nombre de sessions émises : une session absente du backend ou restée `inconnu` compte comme faux négatif, jamais comme succès. `GET /api/mesures` est rapporté à part, comme valeur globale du backend ; backend absent, tout vaut « non mesuré ».
- `--types` limite les types joués, par exemple `--types agent_interne` en mode surface pour faire tourner la vraie passerelle de `interne/`.
- 7 tests ajoutés (`tests/test_bilan.py` et la reproductibilité dans `tests/test_campagne.py`) : deux campagnes successives sur un même backend simulé, format `{"sessions": [...]}` et ancien format, session absente, session non classée, backend absent, types restreints. `cd attaque && uv run --extra dev pytest` donne 23 tests réussis.

### Lancer une campagne mesurable

Toujours contre un backend lancé pour l'occasion, jamais contre le 8700 partagé :

```bash
cd backend && DEDALE_DB=/tmp/banc.db DEDALE_LLM=off uv run uvicorn app.main:app --port 8796
cd attaque && uv run python campagne.py --mode autonome --n 25 --backend http://127.0.0.1:8796
cd attaque && uv run python campagne.py --mode surface --types agent_interne --n 25 --backend http://127.0.0.1:8796
```

Le rapport sort dans `attaque/rapports/campagne-<id>.md` et `.json` (bilan sans manifeste) ; le manifeste complet va dans `attaque/sorties/`, ignoré par git. Dans le markdown : la détection (sessions agent classées `agent_ia` sur sessions agent émises), les faux négatifs avec la part d'absentes et de non classées, les faux positifs (humain ou script classés `agent_ia` sur humain et script émis), le tableau par type avec incidents et suspensions, puis les temps. En mode autonome, le temps de détection suit l'horloge simulée du banc ; la remontée et la latence des POST sont en horloge réelle. Le confinement n'est pas mesuré, faute de décision d'analyste pendant la campagne.

### Ce que les deux campagnes du 10 octobre ont montré

Rapports `campagne-c1010184730f49a` (autonome, 100 sessions) et `campagne-c10101848586937` (surface, 25 sessions d'agent interne). Le trafic d'agent interne que le banc synthétise en mode autonome (trois événements, sans user-agent) reste `inconnu` au classement : 0/25 classées `agent_ia`, alors que le canari ouvre 25/25 incidents et suspend 25/25 sessions. Rejoué par la vraie bibliothèque, il est classé `agent_ia` 25 fois sur 25. C'est un écart de fidélité du banc, pas du backend.

### Reste à faire

- En mode surface, le simulateur d'agent externe ne trouve pas les pièges du vrai `leurres/` : les routes de son `robots.txt` (`/admin/`, `/api/internal/`…) ne figurent pas dans la table du banc, et un essai à deux sessions n'a touché aucun leurre. Il faut lire les leurres touchés depuis le backend plutôt que depuis une table figée dans `banc/surface.py`.
- Sans `--realiste`, les sessions humaines du mode surface arrivent en rafale : dans le même essai, 2/2 sont restées `inconnu`.
- Mesurer le confinement demanderait de jouer aussi la décision d'analyste (`POST /api/incidents/{id}/decision`).
