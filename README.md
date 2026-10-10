# Dédale

Dédale réunit la protection des salariés et des agents IA dans une même console SOC. Un salarié peut suivre un lien trompeur ; son assistant peut obéir à une instruction cachée dans un mail. Le garde du poste avertit le salarié, la passerelle retient l'appel suspect de l'agent, et la boîte noire conserve les événements et les décisions.

Projet du hackathon Secure Horizons (ESSEC, 10-11 octobre 2026), Track 2. Entreprise et données fictives.

Contrats entre modules : [CONTRATS.md](CONTRATS.md).

## Préparer la démo

Il faut Python 3.12 ou plus, `uv`, Node.js, npm et `curl`. Depuis un clone neuf :

```bash
cd console && npm ci && cd ..
cd backend && uv sync && cd ..
cd leurres && uv sync && cd ..
cd interne && uv sync && cd ..
```

Puis, dans deux terminaux à la racine :

```bash
./lancer.sh                  # backend, surface de leurres et console
# Dans un autre terminal :
./demo.sh                    # choix salarié, puis décision de l'analyste dans la console
```

La console de développement est sur `http://localhost:5173`. Le [guide de démonstration](docs/DEMO.md) décrit les choix, les résultats attendus et les commandes de vérification.

## Ce qui fonctionne aujourd'hui

Le prototype utilise des gestes salariés simulés et un agent interne avec des outils locaux. La démo commune emploie un cerveau scripté reproductible ; elle ne dépend pas d'une session Claude disponible. Les événements, incidents, décisions et exports passent par les modules du produit. Le backend recharge son journal SQLite après un arrêt normal ; une base illisible interrompt le démarrage.

Il n'y a pas encore de surveillance native du Mac, de connexion à Outlook/Gmail ou d'intégration à Claude Code. Les appels, chatbots, délégations entre agents et mémoire persistante restent un chantier interrompu. La démo principale ne les utilise pas. Le physique reste une piste d'extension.

Pour un salarié, « annuler » évite le geste simulé et « continuer » ouvre un incident. Le SOC ne coupe pas son poste. Pour un agent, « couper » arrête la session et révoque son jeton ; « reprendre » autorise l'appel retenu. L'envoi d'un rapport dans la démo reste local et fictif.

Les exports ECS/Sigma portent les faits de l'incident. Le texte NIS2 est un brouillon à qualifier et à relire ; aucun envoi réglementaire n'est automatique. Les taux du banc concernent son trafic synthétique et ne prédisent pas une performance en production.

## Modules

- `attaque/` — banc d'attaque et de mesure (agent E). Génère un trafic étiqueté (humain, script, agent IA, agent interne détourné) vers la surface fictive et vérifie la cohérence de la détection. `cd attaque && uv run python campagne.py`.

- **backend/** (agent A) — Console API (FastAPI, port 8700) : collecteur d'événements, tri humain/script/agent IA, dossiers d'incident et boîte noire, brouillon NIS2, exports ECS/Sigma, mesures, flux temps réel WS. Pilier humain « le maillon faible » : sources `humain`/`physique`, surfaces `poste`/`physique`, événement `avertissement` (garde du corps du poste, choix continuer/annuler), cinq incidents `humain_secret`/`humain_mail_externe`/`humain_upload_ia`/`humain_phishing`/`humain_intrusion_physique` avec boîte noire du geste, et compteur « gestes risqués arrêtés vs passés outre ». Règles Sigma (IA + humain) dans **sigma/**. Lancement : `./lancer.sh` (ajouter `--seed` pour une démo).

- **leurres/** (agent B) — Surface exposée d'Orbis Pay : site vitrine + API + doc (FastAPI, port 8701) et serveur MCP leurre (port 8711). 15 leurres `L-xxxx` invisibles pour un humain, saillants pour un lecteur automatique (commentaires HTML, robots.txt/security.txt/ai-plugin.json, faux secrets et identifiants, routes internes, faux outils MCP). Chaque requête émet un événement au backend et applique la consigne reçue (`labyrinthe`, `contre_injection`, `bloquer`) ; labyrinthe déterministe et borné côté serveur. Lancement : `cd leurres && uv run python lancer.py`. Voir [leurres/NOTES-mapping.md](leurres/NOTES-mapping.md) pour les mappings OWASP/ATLAS à confirmer.

- **`console/`** : console web du SOC (Vite + React + TS), commune aux salariés et aux agents IA. Trois vues (salariés par défaut, agents IA, surface externe en réserve), quatre écrans (temps réel, incidents, leurres, mesures). Les incidents exposent la chaîne, le choix du salarié ou la décision de l'analyste, les droits de l'agent et les exports. Voir [console/README.md](console/README.md).
- **`interne/`** — agent IA interne d'Orbis Pay (boîte mail et documents synthétiques, outils natifs et MCP) et passerelle « boîte noire » qui journalise tout, détecte l'exfiltration EchoLeak et l'usage d'un faux secret canari, puis retient l'appel en attendant la décision de l'analyste. V2 : outil MCP piégé par sa description (canari `outil_mcp_piege`, incident `interne_outil_mcp`) et moindre privilège (jeton limité à la tâche, action hors scope bloquée, incident `interne_droits`, vue `GET /api/agents`). Voir [interne/README.md](interne/README.md).
- **`poste/`** : simulateur de gestes salariés (secret collé, mail externe, dépôt vers une IA, phishing). Il affiche un avertissement, laisse choisir `continuer` ou `annuler`, puis envoie le fait au backend quand il est joignable. Il ne surveille pas les applications du poste. Lancement : `cd poste && uv run python -m garde.simulateur`. Voir [poste/README.md](poste/README.md).
- **`landing/`** : page de présentation (HTML/CSS statique). Salariés et agents IA partagent la détection, la boîte noire, les décisions et les exports. Les illustrations de poste montrent la cible produit ; les textes distinguent le prototype des intégrations futures. Ouvrir `landing/index.html`.

## Vérifier

```bash
cd backend && uv run --extra dev pytest
cd ../interne && uv run --extra dev pytest
cd ../poste && uv run --extra dev pytest
cd ../leurres && uv run pytest
cd ../attaque && uv run --extra dev pytest
cd ../console && npm run build
cd .. && python3 -m unittest discover -s scripts/tests
```

Le [plan issu de la session Nila](docs/PLAN_NILA_2026-10-10.md) explique le pitch et les limites. Les supports de jury et la procédure de scan des secrets sont dans `docs/` et `scripts/`.
