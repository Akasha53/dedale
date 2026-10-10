# Dédale

Des pièges que seul un agent IA suit. Dehors, Dédale reconnaît les agents IA qui attaquent la surface exposée d'une entreprise, les perd dans un labyrinthe et leur fait avouer leur objectif. Dedans, il attrape l'agent IA de l'entreprise quand un mail ou un document piégé l'a détourné. Une boîte noire montre au SOC toute la chaîne, et un humain valide chaque riposte forte.

Projet du hackathon Secure Horizons (ESSEC, 10-11 octobre 2026), Track 2. Entreprise et données fictives.

Contrats entre modules : [CONTRATS.md](CONTRATS.md).

## Modules

- `attaque/` — banc d'attaque et de mesure (agent E). Génère un trafic étiqueté (humain, script, agent IA, agent interne détourné) vers la surface fictive et vérifie la cohérence de la détection. `cd attaque && uv run python campagne.py`.

- **backend/** (agent A) — Console API (FastAPI, port 8700) : collecteur d'événements, tri humain/script/agent IA, dossiers d'incident et boîte noire, brouillon NIS2, exports ECS/Sigma, mesures, flux temps réel WS. Règles Sigma dans **sigma/**. Lancement : `./lancer.sh` (ajouter `--seed` pour une démo).

- **leurres/** (agent B) — Surface exposée d'Orbis Pay : site vitrine + API + doc (FastAPI, port 8701) et serveur MCP leurre (port 8711). 15 leurres `L-xxxx` invisibles pour un humain, saillants pour un lecteur automatique (commentaires HTML, robots.txt/security.txt/ai-plugin.json, faux secrets et identifiants, routes internes, faux outils MCP). Chaque requête émet un événement au backend et applique la consigne reçue (`labyrinthe`, `contre_injection`, `bloquer`) ; labyrinthe déterministe et borné côté serveur. Lancement : `cd leurres && uv run python lancer.py`. Voir [leurres/NOTES-mapping.md](leurres/NOTES-mapping.md) pour les mappings OWASP/ATLAS à confirmer.

- **`console/`** — console web du SOC (Vite + React + TS). Les quatre écrans de l'analyste : temps réel, incident (boîte noire), leurres, mesures. Voir [console/README.md](console/README.md).
- **`interne/`** — agent IA interne d'Orbis Pay (boîte mail et documents synthétiques, outils) et passerelle « boîte noire » qui journalise tout, détecte l'exfiltration EchoLeak et l'usage d'un faux secret canari, puis retient l'appel en attendant la décision de l'analyste. Voir [interne/README.md](interne/README.md).
