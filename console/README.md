# Console SOC — Dédale

Écran de l'analyste. Lit l'API du backend (`127.0.0.1:8700`) et son WebSocket
`/ws`. Stack : Vite + React + TypeScript.

Style minimaliste, dans l'esprit de chatgpt.com : police système, fond blanc,
barre latérale #F9F9F9, texte #0D0D0D et gris, boutons en pilule, cartes à
20 px de rayon. Trois couleurs seulement, quand elles portent un sens : rouge
pour le danger et « Couper », orange pour « à décider », vert pour « réglé ».
Ce style est le dernier bloc de `src/index.css` et passe après le reste.

Deux piliers, partagés entre le temps réel et les incidents, ouverts par défaut
sur les **agents IA** (le produit principal) : **Agents IA** (source `interne`)
et **Salariés** (source `humain`). La surface externe et le volet physique
restent dans le backend : la console ne les affiche pas et ne les compte pas.
La page « Leurres » est sortie de la navigation (`src/screens/LeurresView.tsx`
reste en place, la décision est réversible).

Tout le texte visible est en français simple. Les codes du backend (droits,
outils, états) sont traduits dans `src/ui/mots.ts`. Le mot « canary » reste,
avec une infobulle à sa première occurrence (`src/ui/Canary.tsx`).

## Lancer

```bash
cd console
npm install
npm run dev        # dev sur http://localhost:5173
npm run build      # build statique dans console/dist/ (servi par le backend sur 8700)
```

En dev, `/api` et `/ws` passent par le proxy Vite vers `127.0.0.1:8700`
(`vite.config.ts`). Pour viser un autre backend, par exemple une base de test
sur un autre port :

```bash
DEDALE_BACKEND=http://127.0.0.1:8790 npx vite --port 5290
```

## Sans backend

Tant que `/api/mesures` ne répond pas, la console tourne sur des données
simulées (`src/api/mock.ts`, calquées sur CONTRATS.md), sans rien afficher de
particulier. Elle sonde le backend toutes les 5 s et bascule en direct dès
qu'il répond.

## Écrans

1. **Temps réel**. Pour les agents : le fil « Ce que font les agents en ce
   moment » (`GET /api/activite` puis messages WS `activite`), une ligne par
   action, autorisée en vert, retenue en orange, refusée en rouge. Puis la
   liste des agents, avec « Pourquoi ? » : le survol montre l'explication, le
   clic la garde ouverte. Pour les salariés : les postes et les mêmes
   explications.
2. **Incidents**. La liste ne montre que ce qui reste à traiter. Un incident
   réglé (couper, laisser passer, retirer un droit, clore, classer) se barre
   quelques secondes, puis se replie. Les incidents déjà réglés sont sous
   « réglés (n) ». Le détail ouvert reste affiché jusqu'au choix suivant.
3. **Incident d'agent IA** (`src/agent/`). En tête, « Ce qui s'est passé »
   (`GET /api/incidents/{id}/synthese`) : les phrases du copilote, la certitude
   et la décision conseillée. Puis la boîte noire, triée par heure : chaque
   étape se déplie et montre la donnée brute désarmée, pourquoi Dédale l'a
   repérée, ce qu'elle aurait pu provoquer, l'heure précise et les références
   OWASP / ATLAS / ATT&CK, repliées. L'étape « Lecture » ouvre le mail ou le
   document en entier, partie piégée surlignée (`document_source` du maillon
   source, sinon `GET /api/incidents/{id}/source`). À droite, trois choix,
   chacun expliqué en une ligne : couper l'agent, laisser passer l'action,
   retirer un droit (`POST /api/incidents/{id}/retirer-droit`).
4. **Incident salarié**. Le geste, le message affiché par Dédale, le choix du
   salarié, les étapes dépliables, et deux choix : clore ou classer sans suite.
5. **Mesures** : détection, faux positifs, temps de détection et de
   confinement.

## Carte des fichiers

- `src/api/source.ts` — client REST + WebSocket (reconnexion) et sonde backend.
- `src/api/mock.ts` — données simulées, mêmes formes que le backend.
- `src/api/store.tsx` — choix de la source, chargement, flux, bascule vers le direct.
- `src/agent/boiteNoire.ts` — lit le journal de session en étapes simples et
  leur détail ; `preuve.ts` désarme les preuves ; `sources.ts` et
  `ModaleSource.tsx` le contenu lu ; `Synthese.tsx` l'encadré « Ce qui s'est
  passé » ; `Depliant.tsx` le détail d'une étape.
- `src/ui/mots.ts` — vocabulaire simple ; `src/ui/primitives.tsx` — piliers,
  badges, jauges, formats.
- `src/screens/` — un fichier par écran.
