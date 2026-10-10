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
