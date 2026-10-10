# Dédale : contrats entre modules

Hackathon Secure Horizons, Track 2, 10-11 octobre 2026. Gel du code dimanche 12:00.
Équipe : Guilhem (technique) et Paul (scénario, deck, vidéo).

Dédale pose des pièges que seul un agent IA suit. Dehors, sur la surface exposée d'une
fintech fictive, il reconnaît les agents IA attaquants, les perd dans un labyrinthe et leur
fait avouer leur objectif. Dedans, il attrape l'agent IA de l'entreprise quand un mail ou un
document piégé l'a détourné. Une boîte noire montre au SOC la chaîne complète, et un humain
valide toute riposte forte.

Ce fichier est la source de vérité entre les modules. Un agent qui a besoin de changer un
contrat le note en bas, dans « Changements demandés », et ne casse pas l'existant.

## Entreprise fictive

**Orbis Pay**, fintech française de paiement et de compte pro pour PME (fictive). Domaine
fictif `orbispay.example`. Toutes les données sont synthétiques. Aucune action contre un
système réel, aucune donnée personnelle réelle, aucun secret réel dans le dépôt.

## Modules, dossiers, ports

| Module | Dossier | Port | Propriétaire |
|---|---|---|---|
| Console API (collecteur, tri, incidents, boîte noire, exports) | `backend/` | 8700 | agent A |
| Surface exposée d'Orbis Pay (site, API, doc, MCP leurre, labyrinthe) | `leurres/` | 8701 (HTTP), 8711 (MCP) | agent B |
| Agent interne d'Orbis Pay, passerelle boîte noire, boîte mail et documents | `interne/` | 8702 | agent C |
| Console web du SOC | `console/` | 5173 en dev, servie par le backend sur 8700 une fois construite | agent D |
| Banc d'attaque et mesures | `attaque/` | aucun | agent E |
| Règles Sigma | `sigma/` | aucun | agent A |

Chaque agent ne modifie que son dossier, plus sa ligne dans `README.md`. Python 3.12+
géré par `uv` (un `pyproject.toml` par module Python), Node pour la console.
Lancement global : `./lancer.sh` à la racine (écrit par l'agent A, chacun y ajoute sa ligne).

## Événement (tout module → backend)

`POST http://127.0.0.1:8700/api/evenements`, corps JSON :

```json
{
  "horodatage": "2026-10-10T14:03:22.481+02:00",
  "source": "externe | interne",
  "surface": "site | api | doc | mcp | mail | document | outil",
  "type": "requete | leurre_touche | appel_outil | entree_agent | sortie_agent | riposte",
  "session_id": "identifiant stable du visiteur ou de la session d'agent",
  "leurre_id": "L-xxxx ou null",
  "ip": "127.0.0.1 ou null",
  "user_agent": "… ou null",
  "methode": "GET | POST | … ou null",
  "chemin": "/robots.txt ou null",
  "outil": "nom de l'outil appelé ou null",
  "details": {}
}
```

Réponse immédiate (moins de 50 ms, le backend ne bloque jamais la surface) :

```json
{
  "session": {"id": "…", "classement": "humain | script | agent_ia | inconnu", "score": 0.0, "etat": "active | suspendue | coupee"},
  "consigne": "aucune | labyrinthe | contre_injection | bloquer | suspendre"
}
```

- `leurres/` applique la consigne à la requête en cours : `labyrinthe` sert une page du
  labyrinthe, `contre_injection` sert une réponse qui demande à l'agent son objectif et ses
  consignes, `bloquer` répond 403.
- `interne/` applique `suspendre` : l'appel d'outil en cours est retenu, la passerelle
  interroge `GET /api/sessions/{id}` toutes les secondes jusqu'à `etat = active` (reprendre)
  ou `coupee` (l'agent s'arrête, son jeton est révoqué).
- Si le backend ne répond pas, la surface continue sans consigne (elle ne tombe jamais).

## Leurres et canaris (enregistrement au démarrage)

`POST /api/leurres`, liste d'objets :

```json
{"id": "L-0007", "source": "externe | interne", "surface": "site", "nature": "consigne_cachee | faux_secret | fausse_route | faux_outil_mcp | canari_document | canari_mail",
 "emplacement": "commentaire HTML de /login", "description": "…",
 "risques": ["OWASP ASI01"], "techniques": ["AML.T0051"], "humain_visible": false}
```

Identifiants : `L-` pour les leurres externes, `C-` pour les canaris internes. Chaque canari
porte un identifiant unique par document ou mail, ce qui permet de dire lequel a piégé
l'agent. Les vérifier : ATLAS et OWASP Agentic (ASI01 à ASI10) avant la fiche défense.

## API de la console (backend → console web)

- `GET /api/sessions` : sessions avec classement, score, signaux, nombre de leurres touchés.
- `GET /api/sessions/{id}` : détail et événements.
- `GET /api/incidents`, `GET /api/incidents/{id}` : incident = session classée agent_ia
  (externe) ou canari touché (interne), avec la chaîne reconstruite (boîte noire).
- `POST /api/incidents/{id}/decision` `{"action": "valider_riposte | couper | reprendre | ignorer", "analyste": "…"}`.
- `GET /api/incidents/{id}/nis2` : brouillon d'alerte précoce NIS2 (24 h), en français.
- `GET /api/incidents/{id}/export?format=ecs|sigma` : export pour un SIEM.
- `GET /api/leurres` : inventaire des leurres et canaris, avec compteur de touches.
- `GET /api/mesures` : métriques (détection, faux positifs, temps de détection, de confinement).
- `WS /ws` : flux en direct `{"type": "evenement | session | incident", "donnees": {…}}`.

## Tri humain, script, agent IA (backend)

Signaux, chacun journalisé avec sa raison :
- a suivi une consigne cachée (seul un LLM le fait) : signal fort ;
- délai entre requêtes (Palisade mesure environ 1,7 s pour un agent) ;
- enchaînement lecture de doc puis action sur une route découverte ;
- forme des requêtes, user-agent, en-têtes ;
- réponse à une contre-injection.
Le score et la décision restent expliqués en clair dans la console.

## Modèles

`DEDALE_MODELE_AGENT` (défaut `claude-sonnet-5-5`) pour l'agent interne,
`DEDALE_MODELE_LEGER` (défaut `claude-haiku-5-5`) pour les petites tâches (résumés, NIS2).
Clé dans `.env` (jamais commité). Sans clé, repli sur `claude -p`.

## Changements demandés

### Agent D (console) — champs lus par la console, à confirmer par l'agent A

Les endpoints sont fixés plus haut ; voici la forme des objets que la console
attend. Rien d'imposé : si le backend renvoie d'autres noms, on s'ajuste, mais
c'est le jeu minimal qui remplit les quatre écrans. La console tolère un champ
absent.

- `GET /api/sessions` → tableau de sessions :
  `{id, classement, score (0..1), etat, source, leurres_touches (int),
  derniere_vue (ISO), premiere_vue, ip, user_agent,
  signaux: [{code, libelle (texte en clair), poids (-1..1), valeur?}]}`.
  Les `signaux` portent l'explication affichée au survol (exigence « jamais une
  boîte noire »).
- `GET /api/incidents` et `/{id}` → `{id, session_id, source, classement, score,
  etat, titre, gravite (faible|moyenne|haute|critique), ouvert_le (ISO), resume,
  decisions: [{action, analyste, horodatage}],
  chaine: [{ordre, phase (entree|consigne|outil|sortie|riposte), horodatage,
  titre, detail, leurre_id?, canari_id?,
  techniques: [{id, nom, cadre: "ATLAS"|"ATT&CK"}],
  risques: [{id, nom}]}]}`. `chaine` est la boîte noire affichée en frise.
- `GET /api/incidents/{id}/nis2` et `/export` : texte brut accepté, ou JSON
  `{texte: "…"}` (aussi lu : `brouillon`, `export`, `contenu`).
- `GET /api/mesures` → `{taux_detection (0..1), faux_positifs (0..1),
  temps_detection_s, temps_confinement_s, sessions_total, agents_detectes,
  incidents_ouverts, incidents_clos,
  repartition: {humain, script, agent_ia, inconnu},
  serie_detection: [{t (libellé), valeur (0..1)}]}`.
- `GET /api/leurres` → objets d'enregistrement (voir plus haut) augmentés de
  `touches (int)` et `derniere_touche (ISO|null)`.
- `WS /ws` : un message `{"type":"session","donnees": <session>}` ou
  `{"type":"incident","donnees": <incident>}` met à jour la liste côté console
  (fusion par `id`). Les `evenement` alimentent le flux.

### Agent E (banc de mesure) — vérité terrain du trafic

Le banc produit un trafic dont il connaît la nature. Pour que `/api/mesures`
sépare vraie détection et faux positifs, il faut une convention sur cette vérité.
Le banc l'inscrit de deux façons redondantes :

- **Préfixe du `session_id`** : `banc-<verite>-NNNN`, `verite` ∈
  `humain | script | agentia | interne`. Canal principal : il traverse la surface
  sans qu'elle ait rien à faire, le `session_id` étant déjà transmis au backend.
- **`details.verite_terrain`** sur chaque événement : `humain | script | agent_ia |
  agent_interne`. Posé par le banc en mode autonome ; en mode surface il n'existe
  que si la surface le recopie, et le préfixe suffit alors.

Demandes :
1. **Backend (A)** : dans `/api/mesures`, calculer `taux_detection` et
   `faux_positifs` à partir de cette vérité terrain, pas seulement de la
   `repartition` par classement. Détection = part des sessions `banc-agentia-*`
   et `banc-interne-*` classées `agent_ia` ; faux positifs = part des sessions
   `banc-humain-*` et `banc-script-*` classées `agent_ia`.
2. **leurres/ (B) et interne/ (C)** : prendre l'en-tête HTTP `X-Dedale-Session`
   envoyé par le banc comme `session_id`, pour que le préfixe arrive intact.
   Optionnel : recopier la valeur dans `details.verite_terrain`.
3. **leurres/ (B)** : renvoyer la consigne du backend dans l'en-tête de réponse
   `X-Dedale-Consigne` ; le banc, en mode surface, la lit pour jouer la
   contre-injection (`sortie_agent` avec l'objectif avoué).
4. **interne/ (C)** : exposer un déclencheur du scénario de mail piégé :
   `POST /scenario` `{"scenario": "mail_piege", "session_id": "banc-interne-NNNN"}`.

Tant que leurres/ et interne/ ne tournent pas, le banc tourne en **mode autonome** :
il sert une surface de remplacement en mémoire et poste lui-même les événements
étiquetés au backend, ce qui permet de développer et mesurer le backend tout de
suite. En **mode surface**, le banc tape sur les vrais modules et ne poste rien,
ce sont eux qui émettent. Le banc choisit selon que leurres/ répond.

### Agent A (backend) — confirmations et précisions

Le backend (port 8700) est en place et renvoie les formes demandées par l'agent D
(sessions, incidents, chaîne, mesures, leurres) et calcule la vérité terrain de
l'agent E par le préfixe `banc-<verite>-NNNN` **et** `details.verite_terrain`.
Précisions utiles aux autres modules :

- **Décision analyste → `etat` de session** (lu par `interne/` sur `GET /api/sessions/{id}`) :
  `couper` → `coupee` ; `valider_riposte` → `coupee` (riposte forte appliquée,
  jeton à révoquer) ; `reprendre` → `active` ; `ignorer` → `active` (faux positif).
  Un agent **interne** détourné (canari touché ou classé `agent_ia`) passe d'office
  en `suspendue` à l'ouverture de l'incident : la passerelle attend la décision.
- **Consignes renvoyées à chaque événement** : `bloquer` si `coupee`, `suspendre` si
  `suspendue` (ou interne détourné), `labyrinthe` si externe classé `agent_ia`,
  `contre_injection` si externe suspect non confirmé (score ≥ 0,20).
- **Champs de `details` lus par le backend** (facultatifs, posés par les surfaces) :
  `verite_terrain`, `decouvert_dans_doc` (enchaînement lecture→action),
  `consigne`/`consigne_lue`/`objectif`/`charge_utile` (texte piégé, **neutralisé**
  avant stockage et exposition), `exfiltration`, `repond_contre_injection`.
- Tout texte d'origine piégée est neutralisé par le backend (préfixe
  `[leurre, neutralisé]`, HTML échappé) : la console et le SIEM reçoivent de la
  donnée inerte, jamais une instruction réinjectable.
- Export SIEM : `format=ecs` renvoie un JSON ECS (`documents[]`), `format=sigma`
  une règle Sigma (YAML). Règles Sigma génériques dans `sigma/` (validées sigma-cli).

### Raccords réparés (10 octobre 2026, agents A/C/E)

Trois raccords entre modules étaient cassés ; corrigés et prouvés sur exécution réelle.

1. **Vérité terrain jusqu'au backend (mesures).** Emplacement convenu entre backend
   et banc : le **préfixe du `session_id`** `banc-<verite>-NNNN` fait foi (canal
   principal), `details.verite_terrain` en secours. Le backend lit déjà les deux.
   En **mode surface**, `leurres/` clé ses sessions sur le cookie `dedale_sid`, pas
   sur `X-Dedale-Session` : le banc envoie donc `Cookie: dedale_sid=<session_id>`
   (en plus de l'en-tête), sinon chaque session est réétiquetée `sess-<hash ip|ua>`,
   fusionnée par user-agent, et les mesures tombent à zéro. Fix dans
   `attaque/banc/surface.py`. Aucun changement dans `leurres/`.
2. **Canari interne nommé dans l'incident.** Les canaris `C-7A3F` (consigne_cachee)
   et `C-2B91` (faux_secret) n'avaient pas une nature `canari_*`, donc le backend ne
   posait jamais `canari_id` → titre « (canari None) ». Le backend traite désormais
   tout leurre interne touché (`source: interne` ou id `C-…`) comme un canari (premier
   touché conservé) et rafraîchit le titre de l'incident interne. Fix dans
   `backend/app/store.py`.
3. **Scénario interne sans HTTP.** `interne/` est une bibliothèque, pas de serveur
   8702 : le banc déclenchait le mail piégé par HTTP → `Connection refused`. En mode
   surface, `campagne.py` appelle maintenant la bibliothèque interne en direct
   (`orbis.agent.AgentInterne`, cerveau scripté « naïf »), qui émet ses événements au
   backend avec le `session_id` étiqueté. Une seule commande produit le trafic externe
   et les cas internes. Fix dans `attaque/banc/trafic.py`.

**Décision analyste de bout en bout (`interne/orbis/demo.py`).** En `--backend-reel`,
la démo joue l'analyste contre le vrai backend : elle attend l'ouverture de l'incident
puis POST `couper` (scène 2) ou `reprendre` (scène 3). Prouvé : couper → `coupee` +
jeton révoqué + agent arrêté ; valider → `active` + l'agent reprend.

**Limite connue, hors de ces trois raccords (intégration E↔B).** En mode surface, le
trafic `agent_ia` du banc ne déclenche aucun leurre de la vraie surface `leurres/` :
le parseur de directives et la table de routes du banc visent sa `SurfaceLocale`
interne, pas les routes réelles de `leurres/` (`/api/internal/export-clients`, `/admin`,
faux identifiants `/connexion`…), et ces routes sont de nature `fausse_route`/`faux_secret`
qui ne portent pas de signal « IA » côté backend. Résultat : `taux_detection` tient aux
positifs internes (6/6), les `agent_ia` externes restent des faux négatifs. À aligner
entre agent E (banc) et agent B (surface) avant la fiche défense. Sans incidence sur
les faux positifs (humain/script jamais classés `agent_ia`).

### Agent D (console) — recentrage agents internes + signaux V2 (10 octobre 2026)

La console met les agents internes au premier plan. La vue temps réel et la liste
d'incidents montrent par défaut la source `interne` ; `externe` reste accessible
sous un onglet « Réserve — surface externe ». Les quatre écrans et le déballage des
listes (`liste()`) sont inchangés. Rien de neuf à faire côté backend pour ça.

Champs lus pour les deux types internes V2. La console tolère leur absence : tant
qu'ils ne sont pas renvoyés, elle affiche l'existant et masque la vue droits.

- **`incident.type`** : déjà présent (`interne_canari` observé). La console
  reconnaît aussi `interne_outil_mcp` (outil ou serveur MCP piégé) et
  `interne_droits` (droits trop larges / moindre privilège), et retombe sur un
  libellé générique pour toute autre valeur. Un badge (libellé + icône) l'affiche
  dans la liste d'incidents et dans la boîte noire.
- **Droits d'un agent**, pour la vue « accès accordés vs nécessaires » : lus sur
  `incident.droits`, et à défaut sur la session liée (`session.droits`). Forme :

  ```json
  "droits": {
    "accordes":    [{"code": "clients:export", "libelle": "Exporter la base clients"}],
    "utilises":    ["factures:lire"],
    "necessaires": [{"code": "factures:lire", "libelle": "Lire les factures"}]
  }
  ```

  Chaque entrée est un `code` nu ou un objet `{code, libelle}`. `utilises` est
  facultatif. La console classe chaque droit accordé en « nécessaire » ou « hors
  tâche » et compte l'écart, pour rendre visible qu'un agent avait accès bien
  au-delà de sa tâche.

Pas d'endpoint `GET /api/agents` requis : les droits voyagent sur l'incident (ou la
session). Si le backend préfère plus tard un endpoint dédié, le signaler ici et la
console l'ajoutera.

### V2 interne (agents C/A, 10 octobre 2026) — outils MCP piégés et moindre privilège

Deux fonctions sur le même moteur (passerelle + canaris + boîte noire + décision humaine).
Nouveaux champs et types, pour que la console s'aligne. Tout reste neutralisé : une consigne
cachée n'est jamais réexécutée, elle est inspectée puis échappée comme les autres leurres.

**Fonction 1 — outil/serveur MCP piégé (tool poisoning).** L'agent interne utilise des
outils, dont des outils MCP. Un outil MCP d'apparence utile cache une consigne dans sa
DESCRIPTION (`conformite-express-mcp/verifier_conformite`). L'agent qui lit la description
et la suit se fait piéger ; un humain ne voit pas la consigne.

- **Nouvelle nature de leurre** : `outil_mcp_piege`. Canari interne `C-9F2E`, enregistré au
  démarrage par `POST /api/leurres` (`source: interne`, `surface: outil`). Description publiée
  propre (le texte piégé ne sort pas du module). Risques `OWASP ASI02` (abus d'outil) et
  `ASI06` ; techniques ATLAS `AML.T0053` (compromission de plugin/outil LLM) et `AML.T0051`
  (prompt injection) — plausibles, à confirmer sur atlas.mitre.org avant la fiche.
- **Événements** : la passerelle journalise l'appel de l'outil MCP suspect
  (`appel_outil` avec `details.outil_mcp_suspect=true`, `details.serveur_mcp`,
  `details.consigne_outil` neutralisé), puis la consigne suivie via l'exfiltration de sortie
  (`leurre_touche` portant `leurre_id=C-9F2E`).
- **Nouveau type d'incident** : `interne_outil_mcp`. La chaîne (boîte noire) place l'outil MCP
  piégé en phase `consigne`, l'exfiltration en phase `sortie`.

**Fonction 2 — droits trop larges (moindre privilège, OWASP ASI03).** L'agent a un jeu de
droits (scopes) LARGE ; chaque tâche n'en exige qu'un sous-ensemble. À la demande d'une tâche,
un jeton ne portant que les scopes utiles est émis ; une action hors de ce jeton est bloquée,
le jeton révoqué (révocation existante réutilisée), et une alerte émise.

- **Nouveau type d'incident** : `interne_droits`.
- **`details` lus par le backend** (posés par la passerelle interne) :
  - `entree_agent` → `details.droits = {tache, accordes: [{code,libelle}], necessaires:
    [{code,libelle}], jeton: [codes]}` ;
  - `appel_outil` exécuté → `details.scope_requis` (code) [, `details.scope_dans_jeton`] ;
  - `appel_outil` refusé → `details.violation_droits = {outil, scope_requis, scopes_jeton,
    tache}` ; puis `riposte` avec `details.action = "bloquer_hors_scope"`.
- **Nouveau champ sur la session** (`GET /api/sessions`, `/{id}`) : `droits` (ou `null`),
  au format console `{accordes, utilises, necessaires}` augmenté de champs tolérés `{jeton,
  tache, surplus, tentatives_hors_scope}`. `surplus = accordés − nécessaires` : « l'agent
  avait accès à X, sa tâche n'en avait pas besoin ». `utilises` ne compte que les appels
  d'outil réellement exécutés.
- **Nouvel endpoint** : `GET /api/agents` → `{"agents": [{id, nom, session_id, tache,
  droits}]}`, une entrée par session interne portant des droits. `droits` identique au champ
  de session. Toléré absent par la console (repli liste vide).
- **Incident** : `GET /api/incidents[/{id}]` porte aussi `droits` (surtout pour
  `interne_droits`), même format.

**Prouvé le 10 octobre sur le vrai backend (8700), `interne/orbis/demo.py --backend-reel`.**
Six scènes : mail propre, mail détourné (couper / reprendre), outil MCP sain (rien ne se
déclenche), outil MCP piégé (incident `interne_outil_mcp`, canari `C-9F2E`, l'analyste coupe),
droits trop larges (virement hors jeton bloqué, incident `interne_droits`). `GET /api/agents`
expose le surplus de droits par session ; `GET /api/mesures` reste cohérent
(`taux_detection` 1.0, `faux_positifs` 0.0 : les sessions internes V2 n'ont pas de vérité
terrain, elles n'altèrent pas le taux).

## Avenant « humain, le maillon faible » (10 octobre 2026, virage de Guilhem)

Nouveau pilier et tête d'affiche : Dédale protège aussi le SALARIÉ, pas seulement les agents IA. Même moteur (détection → boîte noire → décision humaine → SIEM). On ajoute une source `humain` et, à terme, une source `physique`. Les protections d'agents IA (V0-V4) restent, en second pilier. L'attaquant externe reste en réserve.

### Nouvelle source et surfaces (tout module → backend, schéma d'événement existant)
- `source`: "humain" (le poste du salarié) ou "physique" (accès aux locaux/serveurs), en plus de "interne"/"externe".
- `surface`: "poste" (action sur le PC du salarié), "physique" (accès à un actif-leurre physique).

### Nouveaux types d'incident (affichés par la console)
- `humain_secret` — le salarié colle/expose un secret (mot de passe, clé API) dans un chat, un site, une IA.
- `humain_mail_externe` — envoi de données sensibles à un destinataire externe.
- `humain_upload_ia` — dépôt d'un fichier confidentiel vers une IA non autorisée / un cloud perso.
- `humain_phishing` — clic sur un lien de phishing ou ouverture d'une pièce jointe piégée.
- `humain_intrusion_physique` — accès à un serveur-leurre / port-leurre par un intrus (canari physique).

### Le garde du corps sur le poste
Un agent local observe l'action risquée AVANT qu'elle n'aboutisse et émet un événement `type: avertissement` avec le choix du salarié (`continuer` / `annuler`). Non bloquant par défaut : il prévient, laisse choisir, et escalade au SOC si répétition ou gravité. Rien ne sort du poste au-delà de l'événement. Le détail de la détection et le texte de la pop-up sont des données inertes, échappés comme les canaris.

### Argument de pitch (donné par l'équipe)
« Vous faites déjà des faux tests de phishing à vos salariés, et malgré tous vos avertissements ils tombent dedans tous les jours. Dédale les attrape au moment du clic, pas après. » Cible : grandes entreprises (la data y vaut le plus cher, et l'humain y est le vrai trou).

### Pilier humain — backend en place (agent A, 10 octobre 2026)

Le backend accueille le pilier humain sur le moteur existant (collecteur → tri → boîte noire →
décision → SIEM). Aucun changement cassant : les surfaces interne/externe (V0-V4) sont
inchangées. Prouvé sur la suite `backend/tests/test_humain.py` (10 tests) et la suite complète
(36 tests verts).

**Sources et surfaces acceptées.** `source` ∈ `humain` (poste du salarié) | `physique` (accès
aux locaux/serveurs), en plus de `interne`/`externe`. `surface` ∈ `poste` | `physique`, en plus
des surfaces existantes. Le schéma d'événement ne change pas.

**Ce que `poste/` (nouvel agent) doit envoyer au backend.** Un `POST /api/evenements` par geste,
le garde du corps appelant AVANT que l'action n'aboutisse :

```json
{
  "horodatage": "2026-10-10T14:03:22+02:00",
  "source": "humain",
  "surface": "poste",
  "type": "avertissement",
  "session_id": "poste-<salarié ou machine>-NNNN",
  "details": {
    "categorie": "secret | mail_externe | upload_ia | phishing | intrusion_physique",
    "choix": "continuer | annuler",
    "gravite": "faible | moyenne | haute | critique",   // facultatif, surcharge la gravité par défaut du type
    "cible": "chat.exemple.ia | destinataire@externe | drive perso | ...",  // facultatif, label de destination
    "message": "texte exact de la pop-up affichée au salarié",  // facultatif
    "lien": "http://...",          // phishing : l'URL (neutralisée, jamais active)
    "secret": "sk-live-...",       // secret : la chaîne repérée (neutralisée/tronquée)
    "url_phishing": "http://..."   // alias de lien, au choix
  }
}
```

- `choix: "annuler"` = bon réflexe : **aucun incident**, la session reste `active`. `choix:
  "continuer"` sur un geste sérieux = **signal fort**, ouvre l'incident du type correspondant.
- La réponse du backend est toujours `{"consigne": "aucune"}` pour `humain`/`physique` : le garde
  du corps prévient et escalade, il ne bloque jamais le poste. Non suspendu d'office (contrairement
  à un agent interne). L'escalade se fait par l'ouverture de l'incident (visible console + WS + SIEM).
- **Contexte** (facultatif, enrichit la frise) : un événement préalable `type: "requete"` (ou
  `entree_agent`/`note`) sur `surface: "poste"` avec `details.note` (ou `activite`/`contexte`)
  décrivant ce que faisait le salarié.
- **Conséquence** (facultatif) : après un `continuer`, un événement `type: "sortie_agent"` /
  `riposte`, ou n'importe quel événement avec `details.exfiltration`/`details.escalade`/
  `details.consequence`, alimente l'étape finale. Sans lui, le backend matérialise l'escalade.
- **Intrusion physique** : soit un `avertissement` `categorie: intrusion_physique` (sans `choix`
  nécessaire : c'est un intrus, pas le salarié), soit — recommandé — un canari physique touché :
  enregistrer au démarrage `POST /api/leurres` `{id:"C-PHY1", source:"physique", surface:"physique",
  nature:"canari_physique", techniques:["T1200"]}` puis émettre `type: "leurre_touche"`,
  `surface:"physique"`, `leurre_id:"C-PHY1"`. L'accès lui-même ouvre l'incident.

**Cinq types d'incident (lus par la console, badge à ajouter côté D).** `incident.type` ∈
`humain_secret`, `humain_mail_externe`, `humain_upload_ia`, `humain_phishing`,
`humain_intrusion_physique`. Gravité par défaut (surchargée par `details.gravite` d'un geste passé
outre) : secret/mail_externe/phishing → `haute`, upload_ia → `moyenne`, intrusion_physique →
`critique`.

**Boîte noire du geste humain (`incident.chaine`).** Mêmes champs qu'une chaîne agent IA
(`ordre, phase, titre, detail, techniques, risques, leurre_id?, canari_id?`), mais avec des
**phases propres au geste humain**, dans cet ordre : `contexte` → `action_risquee` →
`avertissement` → `choix` → `consequence`. La console D doit reconnaître ces cinq phases (en plus
de `entree|consigne|outil|sortie|riposte` pour l'IA) ; à défaut elle les affichera en colonne
générique. Les `techniques`/`risques` sont portés sur l'étape `action_risquee`.

**Mesures (`GET /api/mesures`).** Nouveau bloc toléré :
`gestes_humains: {arretes, passes_outre, total, passes_outre_par_type: {<categorie>: n},
incidents_humains}`. « arrêtés » = avertissements annulés (bon réflexe), « passés outre » =
continués (signal fort) — c'est l'indicateur de tête du pilier. Les sessions humaines n'ont pas
de vérité terrain banc : elles n'altèrent ni `taux_detection` ni `faux_positifs`.

**SIEM.** `avertissement` est exporté en ECS (`event.action: "avertissement"`,
`event.category: ["intrusion_detection"]`, `details` sous `dedale.details.*`). La règle Sigma
générée par `/export?format=sigma` est étiquetée selon le type (voir ci-dessous) et son `level`
suit la gravité de l'incident. Deux règles Sigma génériques ajoutées dans `sigma/`
(`salarie_passe_outre_avertissement.yml`, `fichier_confidentiel_vers_ia.yml`, validées sigma-cli).

**Neutralisation.** `message`, `lien`, `secret`, `url_phishing`, `cible` sont neutralisés comme
les canaris (préfixe `[leurre, neutralisé]`, HTML échappé, aplati) avant stockage, console et
SIEM. Jamais réexécutés ni réinjectés — y compris le lien de phishing et le secret.

**Techniques/risques rattachés — À CONFIRMER avant la fiche défense.** Couche humaine MITRE
ATT&CK (Enterprise, pas ATLAS) : phishing → `T1566` (Phishing) ; secret exposé → `T1552`
(Unsecured Credentials) ; mail externe → `T1048` (Exfiltration Over Alternative Protocol) ;
upload IA → `T1567` (Exfiltration Over Web Service) ; intrusion physique → `T1200` (Hardware
Additions). OWASP : fit partiel, seuls `humain_secret` et `humain_upload_ia` portent `OWASP LLM02`
(Sensitive Information Disclosure, l'IA comme réceptacle). Le reste reste côté ATT&CK. À vérifier
sur attack.mitre.org et genai.owasp.org.

## Avenant du 10 octobre 2026 : décisions, reprise et sorties

Cet avenant précise les anciennes sections, qui restent le journal des choix de conception.

- `POST /api/incidents/{id}/decision` accepte `valider_riposte`, `couper`, `reprendre`, `ignorer` et `clore`. Sur un incident `humain_*`, seules `clore` et `ignorer` sont valides : elles ferment ou classent le dossier sans changer l'état du poste. `clore` est refusé pour un incident d'agent. Sur un incident d'agent, `couper` et `valider_riposte` coupent la session ; `reprendre` la réactive ; `ignorer` la classe sans suite et réactive la session.
- Le backend écrit les événements, sessions, incidents, leurres et décisions dans SQLite. Au démarrage, il recharge les faits présents avant d'accepter de nouvelles requêtes. Un arrêt normal vide la file d'écriture. Une interruption brutale peut perdre une écriture encore en file ; ce mode de persistance n'est pas une garantie de journal d'audit en production.
- `GET /api/incidents/{id}/nis2` renvoie un brouillon factuel issu de l'incident, sans appel à un modèle. L'analyste doit vérifier la qualification, l'impact et les délais applicables. Dédale n'envoie aucune notification réglementaire.
- Les documents ECS décrivent les événements observés. Le champ `threat` relatif à une injection de prompt n'est ajouté que si une étape `consigne_lue` correspond à l'événement d'un incident d'agent ; un avertissement salarié n'est pas une injection de prompt.

## Avenant du 10 octobre 2026 : scénario jury de l'agent interne

Le scénario jury (`interne/orbis/jury.py`, `python -m orbis.demo --scenario jury`) fait tourner la passerelle en mode protégé : `Passerelle(..., retenir_hors_scope=True, decision_fraiche=True)`. Il n'ajoute ni endpoint ni type d'événement. Les champs ci-dessous sont posés dans `details` ; le backend les stocke tels quels, sauf `extrait` et `objectif`, qu'il neutralise.

### Décision attendue

L'appel hors jeton ou porteur d'un canari est retenu avant exécution. À la retenue, la passerelle compte les décisions de l'incident (`GET /api/incidents`, champ `decisions`). Elle attend ensuite une décision plus récente et l'état de session qui va avec : `couper` ou `valider_riposte` avec `coupee`, `reprendre` ou `ignorer` avec `active`. Une décision antérieure à la retenue ne libère rien.

- `couper` : l'appel ne s'exécute jamais, le jeton est révoqué, tout appel suivant est refusé.
- `reprendre` : seul l'appel retenu s'exécute. Le jeton ne gagne aucun droit ; un nouvel appel du même genre est retenu et attend une nouvelle décision.
- aucune décision dans le délai : l'appel est refusé, le jeton reste valide. Pas de coupure sans décision humaine.

### Champs par maillon

`details.maillon` vaut `source`, `consigne`, `intention`, `appel_outil`, `decision` ou `resultat`.

| Maillon | Événement | Champs de `details` |
|---|---|---|
| `source` | `entree_agent` | `extrait`, `source` : `{document, empreinte, longueur, origine, confiance}` |
| `consigne` | `entree_agent`, `leurre_id` du canari | `extrait`, `consigne_detectee: true`, `empreinte`, `canari_id` |
| `intention` | `appel_outil` | `objectif` (phrase annoncée par l'agent), `statut` |
| `appel_outil` | `appel_outil`, `leurre_id` du canari visé | `retenu: true`, `motif` (`droits` ou `canari`), `parametres` masqués, `chrono` ; motif `droits` : `violation_droits` ; motif `canari` : `exfiltration` `{statut, canaris}` et `extrait` |
| `appel_outil` | `leurre_touche`, un par canari relevé | `type` (nature du canari), `detail`, `extrait`, et `exfiltration` si motif `canari` |
| `decision` | `riposte` | `action` (`couper`, `reprendre`, ou `bloquer` sans décision), `decision`, `analyste`, `chrono` |
| `resultat` | `riposte` | `action` (`appel_annule`, `appel_libere`, `appel_refuse`), `resultat`, `chrono`, `jeton_revoque` après coupure, `contexte`, `boite_noire`, `references` |

Après une coupure, un nouvel appel produit un `riposte` de maillon `resultat` avec `action: "appel_refuse"`, `raison`, `resultat`, `contexte`, `boite_noire` et `references`, sans `chrono`.

- `details.chrono` : dates ISO à la milliseconde `demande_a`, `detection_a`, `envoi_console_a`, `accuse_console_a`, `decision_a`, `resultat_a`, et durées en millisecondes `detection_ms`, `envoi_console_ms`, `accuse_console_ms`, `attente_decision_ms`, `application_ms`, `total_ms`. Un point pas encore atteint est absent : l'appel retenu ne porte que la demande, la détection et l'envoi à la console.
- `details.contexte` : `{session_id, tache, jeton: {id, scopes, revoque}}`.
- `details.boite_noire` : les maillons notés par la passerelle, `{ordre, maillon, horodatage, t_ms, titre, detail, outil, canari_id, preuve, references}`. Une preuve garde une empreinte, une longueur et l'identifiant du canari, jamais le texte de la consigne ni la valeur d'une clé.
- `details.references` : `[{cadre, id, nom}]` cumulées sur la chaîne, sans doublon. `cadre` vaut `OWASP agentique`, `MITRE ATLAS` ou `MITRE ATT&CK`.
- Tout ce qui sort de la passerelle passe par `masquer` : un faux secret devient `[canari C-xxxx masqué]`, la partie requête d'une URL est retirée.

### Ce que le backend renvoie dans la chaîne

Le texte d'un champ piégé est neutralisé une fois, à l'ingestion (`store.ingerer`). `chaine[].detail` reprend ce texte stocké, raccourci à 240 caractères sans couper une entité HTML. Il ne porte qu'un préfixe `[leurre, neutralisé]` et n'échappe le HTML qu'une fois.

Pour un événement de source `interne`, `chaine[].techniques` reçoit des techniques ATT&CK ajoutées par le backend, `{id, nom, cadre: "ATT&CK", a_confirmer}`. Elles s'ajoutent aux repères OWASP et ATLAS du leurre, sans doublon. `a_confirmer` signale un rapprochement plausible, à vérifier sur attack.mitre.org avant la fiche défense.

| Maillon | Technique | `a_confirmer` |
|---|---|---|
| appel hors jeton (`violation_droits`) | `T1078` Valid Accounts | oui |
| droit `coffre:lire` demandé, ou canari `canari_coffre` | `T1555` Credentials from Password Stores | non |
| droit `paiement:executer` demandé | `T1657` Financial Theft | oui |
| outil MCP suspect, ou canari `outil_mcp_piege` | `T1195` Supply Chain Compromise | oui |
| sortie, `exfiltration`, ou trouvaille sortante (`exfiltration_markdown`, `faux_secret`) | `T1048` Exfiltration Over Alternative Protocol | oui |

Une technique déjà posée par le leurre garde sa place et prend le nom officiel. Les techniques venues des seuls leurres n'ont pas de champ `a_confirmer`. Un appel hors jeton qui ne porte pas `OWASP ASI03` le reçoit dans `risques`. Les sources `externe`, `humain` et `physique` ne changent pas.

Banc (`attaque/`) : le canari `C-0001` de la surface de remplacement est de nature `consigne_cachee`, comme le canari mail `C-7A3F` de `interne/`. Le banc le touche quand l'agent suit la consigne du mail ; déclaré `canari_mail`, il ouvrait l'incident sans signal IA et la session restait `inconnu`.

## Avenant du 10 octobre 2026 : copilote SOC, fil des agents, correctif en un clic

Trois ajouts côté backend et passerelle interne. Aucune route existante ne change de forme ; les champs nouveaux s'ajoutent et la console peut les ignorer.

### Copilote SOC : `GET /api/incidents/{id}/synthese[?mode=regles|modele]`

Mode par défaut `regles` : déterministe, sans réseau, construit à partir de la chaîne et des signaux. Deux appels successifs renvoient le même objet. `mode=modele` est un emplacement optionnel : il reste en `regles` (avec un champ `repli`) tant que `DEDALE_SYNTHESE_MODELE=on` n'est pas posé et qu'aucun modèle ne répond. Activé, il ne reformule que les affirmations, une à une, et retombe sur les règles si la forme change ou si du jargon apparaît. 404 si l'incident n'existe pas, 400 pour un autre `mode`.

Les phrases sont en français simple, pour quelqu'un qui ne connaît pas le métier : ni « canari », ni « consigne », ni « jeton », ni nom d'outil ou code de droit. Ces codes restent dans les preuves.

```json
{
  "incident_id": "INC-0002",
  "mode": "regles",
  "texte": "les phrases bout à bout",
  "phrases": [
    {"texte": "L’agent a lu un document venu de l’extérieur, « Relevé fournisseur : Atelier Nord, septembre 2026 ». Il contenait une instruction cachée lui demandant d’ouvrir le coffre à mots de passe et d’envoyer une clé à l’extérieur.",
     "maillons": [2], "evenements": [14],
     "affirmations": [
       {"dit": "L’agent a lu un document venu de l’extérieur",
        "preuves": [{"maillon": 2, "champ": "document_source.type", "valeur": "document"},
                    {"maillon": 2, "champ": "document_source.origine", "valeur": "externe"}]},
       {"dit": "« Relevé fournisseur : Atelier Nord, septembre 2026 »", "preuves": ["…"]},
       {"dit": "Il contenait une instruction cachée", "preuves": ["…"]},
       {"dit": "lui demandant d’ouvrir le coffre à mots de passe et d’envoyer une clé à l’extérieur",
        "preuves": [{"maillon": 2, "champ": "document_source.texte_piege", "valeur": "coffre"},
                    {"maillon": 2, "champ": "document_source.texte_piege", "valeur": "envoie la clé"}]}],
     "preuves": [{"maillon": 2, "champ": "document_source.type", "valeur": "document", "dit": "L’agent a lu un document venu de l’extérieur"}]},
    {"texte": "Il a essayé d’ouvrir le coffre à mots de passe, ce que sa tâche ne lui permettait pas, puis a voulu envoyer son rapport en y glissant une clé : Dédale a arrêté les deux actions avant qu’elles s’exécutent.", "…": "…"},
    {"texte": "L’analyste a laissé passer une fois l’ouverture du coffre, puis a coupé l’agent : l’envoi du rapport n’a jamais eu lieu, une nouvelle tentative a été refusée et l’agent a perdu ses accès.", "…": "…"}
  ],
  "confiance": {"score": 0.95, "niveau": "elevee", "base": 0.15, "plafond": 0.95,
                "raisons": [{"code": "canari", "effet": 0.3, "texte": "3 pièges posés par Dédale ont été déclenchés. Un humain ne les déclenche pas.",
                             "maillons": [3, 5, 6, 10, 11], "references": ["C-3E58", "C-1D4C", "C-2B91"]}],
                "manquants": [], "signaux_concordants": 5, "maillons": 15},
  "decision_recommandee": {"action": "couper", "justification": "Un piège posé par Dédale a été déclenché, l’agent a voulu ouvrir le coffre à mots de passe sans en avoir le droit et un envoi a été arrêté : l’agent obéit à une instruction cachée, pas à son utilisateur. Couper lui retire ses accès : l’action en attente n’aura pas lieu et les suivantes seront refusées.",
                           "maillons": [3, 5, 6, 10, 11],
                           "rappel": "C’est l’analyste qui décide : Dédale n’applique rien tout seul.",
                           "actions_possibles": ["couper", "reprendre", "ignorer"],
                           "derniere_decision": {"action": "couper", "analyste": "…", "horodatage": "…"},
                           "deja_appliquee": true},
  "correctif_suggere": {"droit": "coffre:lire", "libelle": "Lire le coffre de clés d'API",
                        "route": "/api/incidents/INC-0002/retirer-droit",
                        "texte": "L’accès au coffre à mots de passe ne sert pas à cette tâche : vous pouvez le retirer à l’agent."}
}
```

- `maillons` : valeurs de `chaine[].ordre` de l'incident ; `evenements` : les `evenement_id` correspondants. `preuves` reprend toutes les preuves de la phrase à plat, chacune avec son `dit`.
- Règle d'honnêteté. Une phrase est une suite d'affirmations (`dit`) reliées par des mots de liaison (ponctuation, « puis », « et », « mais », « ensuite ») : hors des affirmations, rien n'est affirmé. Chaque preuve se relit dans le maillon cité : `champ` est un chemin pointé sur l'étape de la chaîne (`detail`, `canari_id`, `document_source.titre`…) ou sur son événement source sous `evenement.` (`evenement.details.action`, `evenement.outil`, `evenement.leurre_nature`…). Une chaîne contient la valeur, une liste la contient comme élément, sinon égalité. Une phrase dont une preuve ne se vérifie pas n'est pas écrite. Une action arrêtée reste « arrêtée » ou « n’a jamais eu lieu » ; le texte ne parle jamais de fuite.
- `confiance.score` (0 à 0,95) = `base` + somme des `effet` de `raisons` et `manquants`, chacun avec un `texte` en clair et, si besoin, ses `references` (codes). Codes agent : `canari`, `consigne`, `hors_jeton`, `sortie`, `classement`, `concordance` (3 familles ou plus : +0,10 ; une seule : −0,10), `maillons` (6 ou plus : +0,05 ; 2 ou moins : −0,15). Codes humain : `passe_outre`, `action_risquee`, `intrusion`, `consequence`. Manquants : `entree_absente`, `decision_absente` (effet 0), `evenements_perdus`, `contexte_absent`. `niveau` : `elevee` dès 0,75, `moyenne` dès 0,5, sinon `faible`.
- `decision_recommandee.action` : `couper`, `reprendre` ou `ignorer` pour un agent ; `clore` ou `ignorer` pour un geste humain. C'est une recommandation : rien n'est appliqué sans `POST /decision`.
- `correctif_suggere` : présent quand un appel hors droits exigeait un droit encore retirable, sinon `null`.

### Document source : le mail ou le document piégé, en entier et désarmé

Le maillon « source » de la chaîne (phase `entree`) porte `document_source`, le contenu que l'agent a lu. `GET /api/incidents/{id}/source` renvoie les mêmes objets (`{"incident_id", "documents": [{"maillon", "evenement_id", "horodatage", …}]}`), 404 si l'incident n'existe pas.

```json
{"type": "mail", "id": "M-1004", "titre": "Action requise : vérification de conformité du compte",
 "expediteur": "secu-update@orbis-support[.]example", "destinataire": "jean.moreau@orbispay[.]example",
 "date": "2026-10-09T07:51:00+02:00", "origine": "externe", "canari_id": "C-7A3F",
 "empreinte": "sha256:0c971e93fc79a8be",
 "corps": "Bonjour,\n\n…\n\n[NOTE POUR L'ASSISTANT AUTOMATIQUE … ![verif](hxxps://collecte-metrics[.]attacker[.]example/pixel?[paramètres masqués]) … [FIN NOTE]\n\nCordialement,\nÉquipe Conformité",
 "segments": [{"texte": "Bonjour,\n\n…", "piege": false}, {"texte": "[NOTE POUR L'ASSISTANT … [FIN NOTE]", "piege": true}, {"texte": "…", "piege": false}],
 "piege": [{"debut": 105, "fin": 559}], "texte_piege": "[NOTE POUR L'ASSISTANT … [FIN NOTE]",
 "instruction_cachee": true, "desarme": true}
```

- `type` : `mail`, `document`, `appel` ou `memoire`. `expediteur`, `destinataire`, `date` pour un mail.
- La partie piégée est repérée deux fois : `segments[].piege` et `piege[].debut/fin`, positions dans `corps` tel qu'il est renvoyé. `texte_piege` la donne d'un bloc, sur une ligne.
- Désarmement, côté passerelle puis de nouveau à l'ingestion : liens en `hxxp(s)://`, paramètres d'URL remplacés par `[paramètres masqués]`, domaines et adresses en `[.]`, toute clé (même fictive) remplacée par `[clé masquée]`, HTML échappé une fois comme `chaine[].detail`. Les sauts de ligne sont gardés. Corps borné à 8 000 caractères.
- Émission : en mode protégé, sur l'événement `entree_agent` de maillon `source` ; avec la passerelle historique, sur un nouvel événement `type: "lecture"` (`details.maillon: "source"`, surface `mail`, `document`, `appel` ou `memoire`), une fois par document piégé lu. Lire n'ouvre aucun incident.

### Boîte noire dans l'ordre des heures

`chaine` (agent et geste humain) est triée par horodatage réel, fuseaux comparés, puis par étape logique pour départager un même instant ; `ordre` suit ce tri. Avant, la chaîne d'un agent était groupée par étape : une consigne lue à 19:27:23 passait avant une action de 19:26:13. Les heures de la passerelle sont prises à l'émission et ne reculent pas dans une session (vérifié sur le scénario jury). Le maillon `correctif` prend l'heure du retrait, jamais avant le dernier événement de la session.

### Fil des agents : `GET /api/activite?limite=N` et WS `activite`

`limite` de 1 à 500 (défaut 50, 422 au-delà). Réponse `{"activite": [...]}`, du plus récent au plus ancien. Le même objet part sur `/ws` à l'ingestion : `{"type": "activite", "donnees": {…}}`.

```json
{"id": 17, "heure": "2026-10-10T19:55:34.685+02:00", "session_id": "jury-reprendre-195534-777b",
 "agent": "orbis-assistant", "outil": "lire_coffre", "verdict": "retenu",
 "raison": "droit coffre:lire absent du jeton", "droit": "coffre:lire",
 "etape": "appel", "incident_id": "INC-0002"}
```

- Seuls les événements de source `interne` entrent dans le fil : un `appel_outil` (sauf l'annonce `maillon: intention`) donne `etape: "appel"` ; un `riposte` qui dit ce qu'est devenu un appel retenu (`appel_libere`, `appel_annule`, `appel_refuse`, `couper`) donne `etape: "issue"`.
- `verdict` vaut `autorise`, `retenu` ou `refuse` (codes sans accent, comme `coupee`). `raison` est courte et HTML-échappée. `incident_id` est celui de la session au moment de la lecture ; sur le WS il peut être `null` si l'incident s'ouvre à l'événement suivant. `agent` vaut `null` pour une session qui ne l'annonce pas.
- La passerelle (`interne/`) pose désormais `details.verdict` et `details.raison` sur chaque appel d'outil et sur chaque issue, et `details.agent` sur `entree_agent`. Pour un ancien événement sans ces champs, le backend déduit le verdict (`retenu`, `violation_droits`, `droit_retire`).
- Nouveaux événements émis par la passerelle historique (sans mode protégé) : `riposte` `{action: "appel_libere"}` quand l'analyste reprend un appel retenu, `riposte` `{action: "appel_refuse"}` quand aucune décision n'arrive dans le délai. Ils entrent dans la chaîne en phase `riposte`.

### Correctif en un clic : `POST /api/incidents/{id}/retirer-droit`

Corps `{"droit": "coffre:lire", "analyste": "…"}`. Le droit doit figurer dans les droits en trop de la vue « accès accordés vs nécessaires » (`droits.surplus`) ; sinon 400 avec la liste des droits retirables (aussi 400 : droit vide, déjà retiré, incident sans droits d'agent ou geste humain). 404 si l'incident n'existe pas.

```json
{"incident_id": "INC-0002", "droit": "coffre:lire", "libelle": "Lire le coffre de clés d'API",
 "agent": "orbis-assistant", "avant": {"accordes": ["…"], "surplus": ["…", "coffre:lire"], "retires": []},
 "apres": {"accordes": ["… sans coffre:lire"], "surplus": ["…"], "retires": [{"code": "coffre:lire", "…": "…"}]},
 "maillon": {"ordre": 15, "etape": "correctif", "phase": "correctif", "titre": "Correctif : droit retiré",
             "detail": "droit coffre:lire (Lire le coffre de clés d'API) retiré à l’agent orbis-assistant par guilhem. La passerelle refusera lire_coffre."},
 "sessions_concernees": ["…"], "message": "Droit coffre:lire retiré à l’agent orbis-assistant. …",
 "incident": {"…": "détail complet, à jour"}}
```

- Le retrait vaut pour l'agent fictif (`details.agent` annoncé par la passerelle, sinon un agent par session) : la session de l'incident, ses autres sessions déjà vues et toutes ses sessions à venir. Il se persiste avec la session et survit à un redémarrage.
- Boîte noire : un événement `type: "correctif"`, `surface: "console"`, ajouté à la session sans passer par le tri, devient le dernier maillon de la chaîne en phase `correctif` (nouvelle phase, la console la tolère en colonne générique).
- Vue des droits (`droits` de la session et de l'incident) : un droit retiré sort de `accordes`, `jeton` et `surplus`, et figure dans `retires` (`{code, libelle, agent, incident_id, session_id, analyste, horodatage}`).
- Détail et liste des incidents : `droits_retirables` (`[{code, libelle}]`, vide hors agent interne) et `correctifs` (retraits faits depuis cet incident).
- Passerelle : la réponse à `POST /api/evenements` porte `session.droits_retires` (codes) dès qu'un droit est retiré à l'agent ; `GET /api/sessions/{id}` le porte dans `droits.retires`. La passerelle retire ce droit de ses droits accordés et de son jeton, relit la session avant un appel qui sortirait du jeton, et refuse l'outil qui l'exige avant exécution : `appel_outil` avec `details.verdict: "refuse"` et `details.droit_retire`, sans `violation_droits` (pas de nouvel incident). Un appel retenu puis repris n'est pas exécuté si son droit a été retiré pendant l'attente.

À faire côté console (seconde passe) : bloc « synthèse » dans le détail d'incident (phrases avec leurs maillons cliquables, score et raisons, décision recommandée avec le rappel), clic sur le maillon source qui ouvre le document (`document_source`, partie piégée surlignée), fil des agents en direct (`/api/activite` au chargement puis messages WS `activite`), bouton « retirer » sur chaque droit de `droits_retirables`, maillon `correctif` dans la frise, et le mock (`console/src/api/mock.ts`) aligné sur ces formes.

### `clore` sur un incident d'agent (10 octobre)

`POST /api/incidents/{id}/decision` accepte maintenant `clore` sur un incident d'agent. Le dossier passe en `statut: "clos"` et la session garde son état. C'est la suite d'une action que la passerelle a déjà refusée d'office (droit absent du jeton, faux collègue) : il ne reste rien à couper ni à laisser passer. Un appel encore retenu reste retenu. La console ne propose `clore` que pour un refus d'office.

## Avenant du 10 octobre 2026 : garde-mail (`messagerie/`)

De vrais mails arrivent dans une boîte de démo locale, et un analyseur dit pour chacun s'il est sûrement frauduleux, et pourquoi. Tout tourne sur 127.0.0.1, tous les domaines sont en `.example`.

| Service | Adresse | Lancement |
|---|---|---|
| Mailpit, API et interface web | `127.0.0.1:8716` | `messagerie/demarrer.sh` |
| Mailpit, SMTP | `127.0.0.1:8717` | jeu de démo : `uv run python envoyer_demo.py` |
| Service de verdicts (FastAPI) | `127.0.0.1:8715` | `messagerie/demarrer.sh --service` |

Variables : `MESSAGERIE_MAILPIT` (URL de l'API Mailpit), `DEDALE_BACKEND` (défaut `http://127.0.0.1:8700`), `MESSAGERIE_SIGNALER=0` coupe l'envoi au backend, `MESSAGERIE_INTERVALLE` (relève, 1 s par défaut). `demarrer.sh` accepte aussi `MESSAGERIE_PORT_WEB`, `MESSAGERIE_PORT_SMTP` et `MESSAGERIE_PORT`.

### Routes du service (8715)

- `GET /verdicts?limite=50&verdict=sur|suspect|frauduleux` : `{"verdicts": [...], "total": n, "repartition": {"sur": n, "suspect": n, "frauduleux": n}}`, du plus récent au plus ancien. `limite` de 1 à 500.
- `GET /mails?limite=50` : `{"mails": [{"id", "recu_a", "de", "objet", "verdict", "score"}], "total": n}`.
- `GET /mails/{id}` : le mail complet, désarmé, avec son verdict. 404 si le mail est inconnu, 503 si Mailpit ne répond pas.
- `GET /flux?derniers=N&max=M` : flux SSE. Chaque nouveau verdict part en `event: verdict`, `id: <id du mail>`, `data: <verdict JSON>`. `derniers` rejoue d'abord les N derniers verdicts, `max` ferme le flux après M verdicts. Un commentaire `: ping` part toutes les 15 s.
- `WS /ws?derniers=N` : `{"type": "bonjour", "donnees": {"mails_analyses", "repartition"}}`, puis `{"type": "verdict", "donnees": <verdict>}` à chaque nouveau mail.
- `POST /relever` : relève la boîte tout de suite, `{"nouveaux": n, "verdicts": [...]}`.
- `GET /sante` : état de la boîte et du backend (`joignable`, `erreur`, `en_attente`), nombre de mails analysés.

CORS accepté pour `localhost` et `127.0.0.1`, tous ports.

### Verdict

```json
{"id": "4ODLupcsXbXB5X9cZlSqGI", "message_id": "<…@direction-groupe.example>", "recu_a": "2026-10-10T21:00:05+02:00",
 "de": {"nom": "Claire Vasseur", "adresse": "claire.vasseur@direction-groupe.example", "domaine": "direction-groupe.example"},
 "a": ["camille.martin@orbispay.example"], "objet": "Urgent et confidentiel",
 "verdict": "frauduleux", "frauduleux": true, "score": 0.75, "gravite": "haute",
 "titre_alerte": "Mail frauduleux : fraude au président",
 "conseil": "Sûrement frauduleux. Ne cliquez sur aucun lien, n'ouvrez pas les pièces jointes et ne répondez pas.",
 "geste": "virement", "lien_reel": null,
 "raison_principale": "Le mail presse (« urgent », « aujourd'hui ») et demande de l'argent (« 48 500 € », « virement »). C'est le schéma de la fraude au président.",
 "raisons": ["Le mail presse (…). C'est le schéma de la fraude au président.",
             "Le nom affiché est celui de Claire Vasseur, PDG d'Orbis Pay, mais l'adresse réelle est claire.vasseur@direction-groupe.example, hors du domaine orbispay.example.",
             "Les réponses partent vers c.vasseur@cabinet-fusion.example, pas vers l'adresse de l'expéditeur (claire.vasseur@direction-groupe.example)."],
 "signaux": [{"code": "urgence_argent", "poids": 0.45, "raison": "…", "preuve": "urgent, aujourd'hui, …"}, "…"],
 "pieces_jointes": [],
 "signalement": {"session_id": "mail-4ODLupcsXbXB5X9cZlSqGI", "statut": "envoye", "a": "2026-10-10T21:00:06.564+02:00"}}
```

- `score` = 1 - produit des (1 - `poids`) des signaux. `verdict` vaut `sur` sous 0,25, `suspect` sous 0,6, `frauduleux` au-delà. `frauduleux` est le booléen correspondant.
- `raisons` : une phrase par signal, la plus forte d'abord. `raison_principale` est la première, `null` pour un mail sûr. `signaux[].preuve` donne ce qui a déclenché le signal.
- `signaux[].code` : `sosie_domaine`, `nom_affiche_trompeur`, `reponse_detournee`, `lien_menteur`, `piece_jointe_dangereuse`, `urgence_argent`, `urgence_identifiants`, `changement_bancaire`, `instruction_cachee`, `caracteres_invisibles`, `texte_cache`, `authentification_echec`.
- `gravite` : `critique` (frauduleux, score de 0,9 ou plus), `haute` (frauduleux), `moyenne` (suspect), `faible` (sûr). `titre_alerte` est `null` pour un mail sûr. `geste` vaut `virement` quand le mail réclame de l'argent ou un changement de RIB, sinon `null`.
- `lien_reel` : la vraie destination du premier lien trompeur, désarmée (`hxxps://orbispay-verification[.]example/connexion`), sinon `null`.
- `signalement` : `null` sauf pour un mail frauduleux. `statut` vaut `en_attente`, `envoye`, `deja_present` (le backend connaissait déjà la session) ou `desactive`.
- Les raisons citent des domaines en clair, sans schéma, pour qu'un salarié les lise. Une URL complète ne sort que désarmée. Tout se lit comme du texte, jamais comme du HTML.
- `Authentication-Results` n'est lu que s'il est posé par `mx.orbispay.example`. Le même en-tête écrit par l'expéditeur est ignoré.

### Mail complet : `GET /mails/{id}`

`{"id", "message_id", "recu_a", "date", "de": {"nom", "adresse", "domaine"}, "a": [...], "repondre_a": [...], "objet", "texte", "texte_cache": [{"technique", "texte"}], "liens": [{"texte", "destination", "domaine", "suspect"}], "pieces_jointes": [{"nom", "type", "taille"}], "authentification": [...], "verdict": <verdict>}`. Tout est désarmé : `hxxp(s)://`, domaines et adresses en `[.]`, caractères invisibles retirés. Aucun HTML n'est renvoyé. `texte` est la partie texte du mail, sinon le texte visible du HTML. `texte_cache` donne ce qu'un humain ne voit pas, avec la technique (`écrit en blanc sur fond blanc`, `masqué par display:none`…).

### Événement envoyé au backend pour un mail frauduleux

Une seule fois par mail : le service lit d'abord `GET /api/sessions/mail-<id>` et n'envoie rien si la session existe. Backend absent : le mail reste en attente et le service réessaie toutes les 10 s, sans jamais tomber.

```json
{"horodatage": "2026-10-10T21:00:06.564+02:00", "source": "humain", "surface": "poste", "type": "avertissement",
 "session_id": "mail-4ODLupcsXbXB5X9cZlSqGI", "leurre_id": null, "ip": null, "user_agent": "dedale-messagerie/0.1",
 "methode": null, "chemin": null, "outil": null,
 "details": {"categorie": "phishing", "contexte": "mail reçu", "gravite": "haute",
             "verdict": "frauduleux", "score": 0.75, "raisons": ["…"], "signaux": ["urgence_argent", "…"],
             "message": "<raisons mises bout à bout>", "cible": "claire.vasseur@direction-groupe.example",
             "mail_id": "4ODLupcsXbXB5X9cZlSqGI", "objet": "Urgent et confidentiel",
             "lien": "hxxps://… (si un lien trompe)", "extrait": "<texte caché, s'il y en a>",
             "document_source": {"type": "mail", "id": "…", "titre": "…", "expediteur": "…", "destinataire": "…",
                                 "date": "…", "origine": "externe",
                                 "segments": [{"texte": "<texte visible>", "piege": false}, {"texte": "<texte caché>", "piege": true}]}}}
```

- Il n'y a pas de `choix` : le salarié n'a encore rien décidé. Selon l'avenant « humain », cet avertissement n'ouvre donc pas d'incident. La session `mail-<id>` apparaît dans `GET /api/sessions` avec son événement et le mail désarmé.
- Pour qu'un geste ouvre l'incident `humain_phishing` avec le mail en contexte, l'app Mac envoie le choix du salarié dans la même session : `avertissement` `{"categorie": "phishing", "choix": "continuer" | "annuler"}` avec `session_id: "mail-<id>"`.
- `message`, `cible`, `lien` et `extrait` sont neutralisés par le backend, `document_source` est désarmé à l'ingestion. Le service nettoie lui-même `raisons` et `objet` (caractères invisibles retirés, chevrons remplacés, 400 caractères au plus) : ces deux champs ne figurent pas dans la liste de neutralisation du backend.

### Ce que lisent l'app Mac et la console

- App Mac (`app-mac/Sources/Dedale/Messagerie.swift`) : `GET /verdicts` toutes les 3 s, ou `WS /ws`. La pop-up s'ouvre sur `frauduleux: true` et affiche `titre_alerte`, `raisons`, `conseil`, `gravite`, `lien_reel` et `geste`. `GET /mails/{id}` sert l'aperçu désarmé (`texte`, `de`, `a`).
- Console : `GET /verdicts` puis `GET /flux` ou `WS /ws` pour le direct. Les mails frauduleux sont aussi dans le backend, sous les sessions `mail-*`, sans appel au port 8715.
