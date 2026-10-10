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
