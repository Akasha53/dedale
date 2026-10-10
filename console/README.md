# Console SOC — Dédale

Écran de l'analyste. Lit l'API du backend (`127.0.0.1:8700`) et son WebSocket `/ws`.
Stack : Vite + React + TypeScript. Thème sombre « salle de supervision ».

## Lancer

```bash
cd console
npm install
npm run dev        # dev sur http://localhost:5173
npm run build      # build statique dans console/dist/ (servi par le backend sur 8700)
```

En dev, `/api` et `/ws` sont relayés vers `127.0.0.1:8700` par le proxy Vite
(`vite.config.ts`). Les URL restent relatives : le même build marche tel quel
une fois servi par le backend.

## Sans backend

Tant que `/api/mesures` ne répond pas, la console tourne sur un **mock local**
(`src/api/mock.ts`, calqué sur CONTRATS.md) : les quatre écrans sont remplis et
le flux temps réel bouge. Un bandeau le signale. La console sonde le backend
toutes les 5 s et bascule en direct dès qu'il répond, sans rechargement.

## Écrans

1. **Temps réel** — flux des sessions, classement humain / script / agent IA,
   score, et au survol les signaux en clair qui expliquent la décision. Compteurs
   en tête.
2. **Incident** — chaîne « boîte noire » en frise verticale (mail/doc piégé →
   consigne → appels d'outils → sortie de données), techniques MITRE ATLAS/ATT&CK
   et risques OWASP Agentic. Boutons de décision (`POST /api/incidents/{id}/decision`).
   Panneau latéral : brouillon NIS2 et export SIEM ECS/Sigma, avec copie.
3. **Leurres & canaris** — inventaire (`GET /api/leurres`) et compteur de touches.
4. **Mesures** — détection, faux positifs, temps de détection et de confinement,
   en chiffres clés et deux graphes SVG.

## Carte des fichiers

- `src/api/source.ts` — client REST + WebSocket (reconnexion avec backoff) et sonde backend.
- `src/api/mock.ts` — mock local.
- `src/api/store.tsx` — choix de la source, chargement, flux, bascule mock → live.
- `src/screens/` — un fichier par écran. `src/ui/primitives.tsx` — badges, jauges, formats.
