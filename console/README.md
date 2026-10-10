# Console SOC — Dédale

Écran de l'analyste, recentré sur « l'humain, le maillon faible ». Lit l'API du
backend (`127.0.0.1:8700`) et son WebSocket `/ws`. Stack : Vite + React +
TypeScript. Thème sombre « salle de supervision ».

Trois piliers partagés entre le temps réel et les incidents, ouverts par défaut
sur les **salariés** : **Salariés** (source `humain`/`physique` : gestes
risqués interceptés sur le poste), **Agents IA** (agents internes détournés) et
**Réserve — surface externe**. Mapping des types d'incident et libellés/icônes
centralisé dans `src/ui/primitives.tsx` (`TYPE_INCIDENT`, `PILIERS`).

## Lancer

```bash
cd console
npm install
npm run dev        # dev sur http://localhost:5173
npm run build      # build statique dans console/dist/ (servi par le backend sur 8700)
```

En dev, `/api` et `/ws` sont relayés vers `127.0.0.1:8700` par le proxy Vite
(`vite.config.ts`). Les URL restent relatives : le même build marche tel quel
une fois servi par le backend. Pour viser un autre backend, par exemple une base
de test sur un autre port :

```bash
DEDALE_BACKEND=http://127.0.0.1:8790 npx vite --port 5290
```

Les polices (Space Grotesk, IBM Plex Mono, licence OFL) sont dans
`src/assets/fonts` : la console ne charge rien depuis un CDN.

## Sans backend

Tant que `/api/mesures` ne répond pas, la console tourne sur un **mock local**
(`src/api/mock.ts`, calqué sur CONTRATS.md) : les quatre écrans sont remplis et
le flux temps réel bouge. Un bandeau le signale. La console sonde le backend
toutes les 5 s et bascule en direct dès qu'il répond, sans rechargement.

## Écrans

1. **Temps réel** — flux des sessions du pilier choisi, score, et au survol les
   signaux en clair qui expliquent la décision. Compteurs en tête, propres au
   pilier : pour les salariés, salariés surveillés et gestes risqués arrêtés.
2. **Incident d'agent IA** (`src/agent/`) : la boîte noire en six maillons
   datés à la milliseconde (source, consigne, intention, appel d'outil,
   décision, résultat), lue dans le journal de session, avec les preuves rendues
   inertes (liens désarmés, domaines coupés, clés canaris masquées). À droite :
   **Couper** (session coupée, jeton révoqué) et **Reprendre** (libère le seul
   appel retenu, en deux clics), désactivé quand l'action était hors droits ;
   les accès accordés face aux accès nécessaires ; les exports ECS, Sigma et
   NIS2 téléchargeables en un clic. En tête, le chrono détection, remontée et
   décision humaine, et les repères OWASP Agentic / ATLAS / ATT&CK. Sans journal
   (mock), la vue se replie sur la chaîne du backend.
3. **Incident salarié ou externe** : chaîne « boîte noire » en frise verticale, techniques MITRE
   ATLAS/ATT&CK et risques OWASP Agentic. Pour un incident humain, un panneau
   « garde du corps sur le poste » montre le geste risqué, l'avertissement
   affiché et le choix du salarié (annulé = protégé / passé outre = incident).
   Boutons de décision (`POST /api/incidents/{id}/decision`). Panneau latéral :
   brouillon NIS2 et export SIEM ECS/Sigma, avec copie.
4. **Leurres & canaris** — inventaire (`GET /api/leurres`) et compteur de touches.
5. **Mesures** — détection, faux positifs, temps de détection et de confinement,
   en chiffres clés et deux graphes SVG.

## Carte des fichiers

- `src/api/source.ts` — client REST + WebSocket (reconnexion avec backoff) et sonde backend.
- `src/api/mock.ts` — mock local.
- `src/api/store.tsx` — choix de la source, chargement, flux, bascule mock → live.
- `src/agent/` — écran d'incident d'agent IA : `boiteNoire.ts` lit le journal
  en six maillons, `preuve.ts` rend les preuves inertes, `references.tsx` les
  badges OWASP/ATLAS/ATT&CK.
- `src/screens/` — un fichier par écran. `src/ui/primitives.tsx` — badges, jauges, formats.
