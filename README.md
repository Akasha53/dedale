# sAIfe

sAIfe se prononce « safe ». Le code garde le nom de travail `dedale` : nom du dépôt et des dossiers, modules Python, variables `DEDALE_*`, `~/.config/dedale/`, `Dedale.app`, identifiants de bundle et d'extension. Les renommer casserait des chemins et ferait redemander à macOS les autorisations déjà accordées.

[![Scan de secrets : 0 alerte](https://img.shields.io/badge/scan%20de%20secrets-0%20alerte-brightgreen)](docs/SCAN_SECRETS.md)

Projet du hackathon Secure Horizons (ESSEC, 10-11 octobre 2026), Track 2. L'entreprise, les mails, les secrets et les paiements sont fictifs (Orbis Pay). Tout tourne en local, sauf le relecteur IA : quand il a accès à Haiku (API ou `claude -p`), il lui envoie des faits pseudonymisés, jamais le texte d'un mail ; sans accès, ses règles tranchent.

Vidéo de démo (2 à 3 min) : lien à ajouter après le tournage.

## Le problème

Un même contenu piégé vise deux lecteurs. Le salarié peut suivre un lien trompeur, ouvrir un sosie du site de son entreprise ou valider un virement réclamé par un faux dirigeant. Son assistant IA peut obéir à une consigne cachée dans un mail et envoyer des données dehors, comme avec la faille EchoLeak de Microsoft 365 Copilot (CVE-2025-32711). Les outils de sécurité traitent ces deux lecteurs séparément, avec deux journaux et deux consoles.

sAIfe les met dans une même console SOC. Sur le poste, il prévient le salarié avant le geste et le laisse choisir. Côté agent, chaque appel d'outil passe par une passerelle qui retire les consignes cachées avant lecture et retient l'appel suspect avant qu'il parte. Une boîte noire scellée garde les événements et les décisions, et c'est un humain qui tranche.

## Architecture

| Dossier | Rôle | Port |
|---|---|---|
| `backend/` | API de la console (FastAPI) : collecte des événements, tri humain, script ou agent IA, incidents, boîte noire et journal scellé, relecteur IA, règles du SOC, inventaire des agents, rapport d'incident, exports ECS et Sigma, brouillon NIS2, mesures, flux WebSocket | 8700 |
| `console/` | Console du SOC (Vite, React, TypeScript) : temps réel, incidents des agents IA et des salariés, règles du SOC, mesures | 5173 |
| `interne/` | Agent IA interne d'Orbis Pay et sa passerelle : jeton limité à la tâche, canaris, désarmeur des consignes cachées, retenue de tout envoi hors d'Orbis Pay | aucun |
| `messagerie/` | Garde-mail : boîte de démo (Mailpit) et analyseur qui juge chaque mail sûr, suspect ou frauduleux, avec ses raisons | 8715, 8716, 8717 |
| `app-mac/` | App de barre de menus (Swift) : pop-up avant le geste (mail frauduleux, site louche dans Safari ou Chrome, fichier à risque dans Téléchargements), inventaire des agents IA du poste, coach après « Annuler », signalement d'un mail, quatre yeux sur un geste critique, panneau « Ce que sAIfe regarde sur ce poste » | 8712 |
| `extension/` | Extension Chrome : page d'avertissement avant un site sosie ou louche | aucun |
| `poste/` | Simulateur de gestes du salarié (secret collé, mail externe, dépôt vers une IA, phishing) | aucun |
| `attaque/` | Banc de mesure : trafic étiqueté humain, script, agent IA ou agent interne, envoyé à un backend | aucun |
| `scripts/` | `demo_jury.py` (démo du jury en une commande) et scan de secrets | |
| `sigma/` | Règles Sigma utilisées par les exports | |
| `docs/` | Déroulé de la démo, fiche jury, deck, mesures | |
| `landing/` | Page de présentation statique | |

Les formats d'échange entre modules sont dans [CONTRATS.md](CONTRATS.md). Le dossier `leurres/` contient l'ancienne surface exposée aux agents externes, abandonnée le 10 octobre : ni la console ni la démo ne s'en servent.

## Installation

Il faut Python 3.12 ou plus, `uv`, Node.js et npm. Le garde-mail demande Mailpit (`brew install mailpit`), l'app Mac macOS 13 et Swift 5.9. Depuis un clone neuf :

```bash
cd console && npm ci && cd ..
for d in backend interne poste messagerie attaque; do (cd "$d" && uv sync); done
```

L'agent interne tourne par défaut sur un cerveau scripté, sans réseau. Sans clé d'API, le relecteur IA passe par `claude -p` s'il est installé, sinon par ses règles. `.env.example` liste les variables facultatives.

## Lancer la démo

Le déroulé minute par minute est dans [docs/DEMO_JURY.md](docs/DEMO_JURY.md). Chaque ligne part de la racine du dépôt, dans son propre terminal.

```bash
cd messagerie && ./demarrer.sh --service        # boîte de démo et verdicts (8715 à 8717)
cd app-mac && ./construire.sh --lancer          # bouclier dans la barre des menus
./demo.sh jury                                  # à la racine : base neuve, backend, console, scènes, chrono
```

`./demo.sh jury` met l'ancienne base de côté dans `data/sauvegardes/`, repart d'une base vide, lance le backend (8700) et la console (`http://localhost:5173`) s'ils manquent, joue la scène du salarié puis celle de l'agent, et attend la décision de l'analyste. Il ne décide jamais à sa place. `./demo.sh jury --arreter` arrête ce qu'il a lancé.

Autres scènes, depuis la racine :

```bash
cd messagerie && uv run python envoyer_demo.py --cas sosie            # mail sosie : pop-up sur le Mac
cd messagerie && uv run python envoyer_demo.py --cas fraude_president # virement : quatre yeux et relecteur IA
cd interne && uv run python -m orbis.demo --scenario jury --desarmeur --backend http://127.0.0.1:8700
cd poste && uv run python -m garde.simulateur                         # journée de gestes salariés
```

L'extension se charge dans `chrome://extensions`, « Charger l'extension non empaquetée », dossier `extension/`.

## Comment l'humain garde la main

Tout ce qui suit est dans le code au commit `a1a7321`, celui des mesures ; le fichier ou la route est indiqué à chaque fois.

### Le salarié choisit, et il est prévenu avant d'agir

L'app Mac ouvre une pop-up avant le geste, avec une ou deux raisons en clair : un mail jugé frauduleux dans la boîte de démo, un site louche dans l'onglet actif de Safari ou de Chrome, un fichier à risque qui arrive dans Téléchargements. L'extension Chrome affiche une page d'avertissement à la place d'un site sosie. Le salarié choisit « Annuler » ou « Continuer » (« Mettre de côté » ou « Garder » pour un fichier). « Annuler » envoie un événement à la SOC, qui compte un piège évité sans ouvrir de dossier, et affiche un coach de trois lignes. « Continuer » sur un geste sérieux ouvre un incident, mais le backend répond toujours `consigne: aucune` au poste : il ne bloque jamais le salarié (`backend/app/store.py`, avenant « humain » de `CONTRATS.md`).

Seule exception, le geste critique : un virement ou un export de fichiers clients attend un second regard avant de partir. La pop-up le dit avant le choix.

Ce que le poste regarde tient en quatre modules, chacun avec son interrupteur dans le panneau « Ce que sAIfe regarde sur ce poste » (`app-mac/Sources/Dedale/ModulesPoste.swift`) : les mails reçus, l'adresse de l'onglet actif, les nouveaux téléchargements, les agents IA installés. L'analyse se fait sur le poste. Part à la SOC : la catégorie, le domaine et le choix du salarié, l'empreinte d'un fichier, l'inventaire des agents sans secret. La copie désarmée d'un mail jugé frauduleux part du serveur de messagerie (`messagerie/`), pas du poste. Ne sont jamais lus le presse-papiers, les frappes, l'écran, le contenu des pages ni l'historique. Prévu avant un déploiement, et pas encore fait : une durée de conservation (90 jours par défaut), l'information des salariés et la consultation du CSE.

### Le geste critique est relu en quelques secondes, l'analyste garde un recours

Un geste critique va au relecteur IA (`backend/app/relecteur.py`). Haiku le relit par l'API ou par `claude -p` et accorde ou refuse avec un motif d'une phrase. Il ne reçoit que des faits structurés (type de geste, montant, destination interne ou non, salarié sous pseudonyme) ; le texte de la pop-up passe désarmé dans un champ marqué comme donnée. Les règles gardent le dernier mot : elles refusent d'office un virement au-dessus de 10 000 €, un export de clients vers l'extérieur ou un texte qui contient une consigne adressée à une IA, et le modèle ne peut pas accorder ce qu'elles refusent. Une panne, une limite d'usage, plus de 8 s d'attente ou une réponse hors format font retomber sur les règles, qui refusent quand elles ne savent pas trancher. Chaque verdict dit qui a tranché, Haiku ou les règles.

Le verdict s'ajoute aux décisions de l'incident, là où l'app Mac le lit. L'analyste garde « Accorder » et « Refuser » dans la console ; accorder un geste, ou revenir sur le verdict du relecteur, demande un motif, scellé avec la décision. Sans relecteur (`DEDALE_RELECTEUR=off`), l'app attend l'analyste 90 s puis refuse ; un backend injoignable vaut aussi un refus. Le recours de l'analyste corrige le dossier : il ne rattrape pas un geste déjà accordé sur le poste. La pop-up affiche le verdict avec son motif, par exemple « Relu par sAIfe en 3,6 s : accordé. », et la console le montre sur le dossier, avec Accorder et Refuser en recours.

### Couper un agent : confirmation, motif, annulation

Dans la console, « Laisser passer » demande toujours une confirmation. Sur un incident critique, et toujours sur un téléphone, « Couper l'agent » demande aussi une confirmation avec un motif obligatoire, puis laisse cinq secondes pour annuler avant que la décision parte (`console/src/ui/Confirmation.tsx`). L'analyste choisi signe la décision, et le motif entre au journal scellé à côté d'elle (`POST /api/incidents/{id}/decision`). Couper arrête la session et révoque le jeton de l'agent.

Sans décision, rien ne part : l'appel retenu par la passerelle est refusé au bout de son délai d'attente (60 s par défaut, réglable), y compris quand elle ne joint plus le backend (`interne/orbis/passerelle.py`).

### Un journal scellé

Chaque événement, chaque décision et chaque maillon de la boîte noire porte une empreinte SHA-256 chaînée à la précédente (`backend/app/journal_scelle.py`). Les verdicts du relecteur IA, les motifs, les levées d'anonymat et les actions sur le compte d'un salarié entrent dans la même chaîne. `GET /api/incidents/{id}/verification` relit tout le dossier dans la base et nomme ce qui a changé : « altérée à la décision 1 : champ analyste modifié ». `cd backend && uv run python -m app.verifier_journal` passe par la même vérification pour toute la base. Le rapport d'une page pour le RSSI (`GET /api/incidents/{id}/rapport`) imprime le sceau.

Chaque entrée porte en plus la signature Ed25519 de son émetteur : la passerelle des agents, l'app du poste, les leurres, ou le backend pour une décision, au nom de l'analyste. Les agents IA n'écrivent jamais eux-mêmes dans le journal, ils passent par la passerelle. Les clés restent hors du dépôt, dans `~/.config/dedale/cles/`. SQLite refuse ensuite de modifier ou d'effacer une ligne du journal (`backend/app/ancrage.py`).

### Pourquoi Avalanche, et ce qui part sur la chaîne

C'est une voie d'exploration, pas une fonction livrée. Aucune ancre n'est publiée aujourd'hui : l'adresse d'ancrage n'a pas reçu d'AVAX de test.

Le problème qu'elle vise reste entier. Un administrateur de la base peut retirer les déclencheurs, réécrire tout le journal, recalculer chaque empreinte et, s'il tient la machine, re-signer. Contre lui, il faut une copie que personne ici ne peut modifier. L'idée est de publier la racine de Merkle des entrées nouvelles sur la C-Chain de test d'Avalanche (Fuji), à chaque incident clos : une transaction de 0 AVAX de l'adresse d'ancrage vers elle-même, sans contrat. Avalanche est partenaire du hackathon, et sa C-Chain parle le JSON-RPC d'Ethereum : une transaction signée par `eth-account` suffit.

Sur la chaîne partiraient une étiquette (`dedale-ancre-v1:`) et une empreinte de 32 octets, sans texte, sans nom, sans adresse IP. Effacer une donnée personnelle resterait possible dans la base sans toucher à l'ancre : la vérification montrerait cette entrée comme modifiée depuis l'ancrage, et les autres entrées du lot resteraient prouvées une à une.

Ce qui marche déjà, en local : les signatures, l'ajout seul, la vérification champ par champ, et le calcul des racines, qui attendent dans une file sans aucun appel réseau (`DEDALE_ANCRAGE=file`, le réglage par défaut). Le code d'envoi et de relecture sur Fuji est écrit et testé contre un faux nœud ; en lecture, il a lu le bloc courant et le solde de l'adresse sur le vrai réseau. Ce qui manque : alimenter l'adresse (`uv run python -m app.ancrage adresse`), lancer `uv run python -m app.ancrage ancrer`, puis vérifier une première ancre sur Snowtrace. Le badge de la console ne parle que de l'intégrité vérifiée en local.

### L'identité du salarié révélée seulement sur motif

La console montre un pseudonyme stable (« Salarié 4821 · Finance »), jamais un nom ; les paramètres d'URL qui diraient qui a cliqué sont retirés (`backend/app/identites.py`). Lever l'anonymat passe par `POST /api/incidents/{id}/identite` avec un motif de cinq caractères au moins. L'acte est scellé avec son auteur et son motif, et le journal ne garde jamais le nom révélé.

### Des règles écrites en français, confirmées avant activation

L'analyste écrit une phrase, par exemple « L'agent de tri ne doit jamais envoyer de mail hors d'Orbis Pay ». sAIfe répond « Voilà ce que j'ai compris : … Activer ? » et n'active rien sans ce feu vert (`POST /api/politiques/analyser`, puis `POST /api/politiques` ; panneau des règles dans l'écran « Temps réel » de la console). Une phrase incomprise est refusée avec ce qui manque. L'analyse se fait par motifs, sans modèle, sauf si `DEDALE_POLITIQUES_MODELE=on`.

### Seuils d'escalade

| Ce qui arrive | Ce que fait sAIfe | Qui tranche |
|---|---|---|
| Le salarié annule | rien ne remonte comme incident ; le geste est compté | personne |
| Le salarié continue un geste sérieux | incident `humain_*`, gravité haute (moyenne pour un dépôt vers une IA) ; poste jamais bloqué | l'analyste clôt ou classe |
| Geste critique (virement, export de clients) | geste suspendu | relecteur IA, recours de l'analyste |
| Session classée agent IA | score de tri au-dessus de 0,40 (`DEDALE_SEUIL_AGENT_IA`) | la console l'affiche |
| Appel d'agent hors du jeton de sa tâche | appel refusé et jeton révoqué (retenu pour l'analyste dans le scénario du jury) | la passerelle, puis l'analyste |
| Canari touché ou envoi hors d'Orbis Pay | appel retenu avant exécution, agent suspendu, incident | l'analyste coupe, laisse passer ou ignore ; sans décision, l'appel est refusé |
| Consigne cachée retirée par le désarmeur | incident « Consigne cachée retirée avant que l'agent la lise », agent suspendu | l'analyste |
| Comportement inhabituel d'un agent (5 fois plus d'appels et au moins 10 en une minute, outil jamais utilisé, volume lu multiplié par 10) | alerte, l'agent n'est pas suspendu | l'analyste |
| Règle du SOC | bloquer, retenir ou alerter, selon la règle | la règle, écrite et confirmée par le SOC |

Le relecteur IA pré-trie aussi chaque incident (priorité, décision proposée, confiance). Sous une confiance de 0,7, il le marque « doute » et le met dans la file à regarder (`GET /api/relecteur/file`). Il propose, il ne décide rien sur un agent.

### Traçabilité des conclusions de l'IA

La synthèse « Ce qui s'est passé » est écrite par des règles, sans modèle, et chaque phrase renvoie à son maillon de la boîte noire (`GET /api/incidents/{id}/synthese`). La confiance est expliquée raison par raison. Le mode modèle est facultatif ; s'il échoue ou s'écarte des faits, la synthèse par règles revient, avec le motif du repli.

## Métriques

Mesurées le 10 octobre 2026 à 22 h 10 au commit `a1a7321`, sur des backends isolés (port libre, base SQLite temporaire, jamais le backend partagé). Trafic et mails sont synthétiques et écrits pour la démo : ces chiffres montrent que le moteur tient sur ce jeu, pas un taux de détection en production. Détail et dénominateurs : [docs/mesures/resultats.md](docs/mesures/resultats.md).

Tout se rejoue en une commande, qui lance ses propres backends et les arrête :

```bash
python3 docs/mesures/mesurer.py          # 25 sessions par type ; --sans-relecteur pour ne pas appeler Haiku
```

| Mesure | Résultat | Source |
|---|---|---|
| Agent interne piégé, joué par la vraie passerelle | 25/25 sessions classées agent IA, 25/25 incidents, 0 rapport sorti | campagne `c10102210189b77` |
| Temps de détection (premier événement de la session → classement agent IA) | médiane 10 ms, moyenne 11 ms, 25 échantillons | `GET /api/mesures`, `temps_detection` |
| Temps de confinement (détection → session coupée) | médiane 19 ms, moyenne 20 ms, 25 échantillons ; la coupure part d'un script qui relève les incidents toutes les 20 ms | `GET /api/mesures`, `temps_confinement` |
| Ouverture de l'incident après l'événement déclencheur | médiane 0,81 ms, moyenne 1,01 ms, 25 incidents | rapport de campagne |
| Agent IA externe | 25/25 sessions classées agent IA, 25/25 incidents | campagne `c10102210173b01` |
| Faux positifs du tri | 0/50 sessions humaines ou scriptées classées agent IA | campagne `c10102210173b01` |
| Taux de détection sur les 12 mails de démo | 8/8 mails frauduleux repérés ; classe exacte 12/12 | analyseur de `messagerie/` |
| Faux positifs sur les mails | 0/3 mail légitime signalé ; le mail douteux sort « suspect » | analyseur de `messagerie/` |
| Désarmeur sur les 12 mails | consigne cachée retirée dans 2/2 mails qui en portent une, 0/10 ailleurs | `interne/orbis/desarmeur.py` |
| Relecteur IA sur 6 gestes critiques | 6/6 tranchés par Haiku (`claude -p`), aucun repli ; 1 accordé, 5 refusés ; médiane 3,3 s, moyenne 3,6 s | `GET /api/relecteur/demandes/{id}` |

Ce qui n'est pas mesuré : le temps de décision d'un analyste humain, un vrai modèle dans l'agent (le cerveau est scripté), un vrai poste ou une vraie messagerie.

## Tests

555 tests réussis le 10 octobre 2026 à 22 h 12, au commit `a1a7321` : backend 195, interne 162, messagerie 73, attaque 29, leurres 19, poste 17 (pytest), scripts de démo 34 (unittest), extension 26 (`node --test`). Les tests Swift de l'app Mac (`swift test`) ne sont pas dans ce total. Ces tests vérifient le prototype, pas une détection en production. Chaque ligne part de la racine du dépôt.

```bash
cd backend && uv run --extra dev pytest
cd interne && uv run --extra dev pytest
cd poste && uv run --extra dev pytest
cd messagerie && uv run --extra dev pytest
cd attaque && uv run --extra dev pytest
cd leurres && uv run pytest
python3 -m unittest discover -s scripts/tests
cd extension && node --test tests/comparateur.test.js
cd app-mac && swift test
cd console && npm run build        # vérification des types, sans test compté
```

## Authentification

Chaque appel au backend présente le jeton de son identité, dans `Authorization: Bearer`. Quatre identités : `analyste` (la console du SOC), `passerelle` (agents internes, leurres, messagerie, banc), `poste` (app Mac, garde du poste, extension) et `validateur` (l'espace `/validation`, où le responsable ou la finance confirme un geste métier). La passerelle et le poste écrivent des événements et attendent une décision, ils n'en prennent aucune. Sans jeton : 401. Avec le jeton d'une autre identité : 403. Une route qui ne déclare rien n'admet que l'analyste. Seule `GET /api/sante` reste ouverte. Chaque refus est journalisé sans le jeton et compté dans `GET /api/mesures` (`acces_refuses`).

Les jetons vivent dans `~/.config/dedale/jeton-<identité>` (dossier en 700, fichiers en 600), jamais dans le dépôt. Le backend les tire au premier démarrage ; chaque module relit le sien. La console ne le reçoit jamais : le proxy de Vite (5173) ajoute l'en-tête côté serveur, et seulement pour un navigateur qui a ouvert la page. L'extension Chrome attend le jeton du poste dans ses réglages.

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8700/api/incidents/INC-0001/decision \
  -H 'content-type: application/json' -d '{"action":"accorder","analyste":"Marc"}'   # 401
```

Limite : un jeton par identité, pas par personne. Le nom qui signe une décision est celui que déclare la console, et tout navigateur de ce Mac qui ouvre la console agit comme analyste. En production il faudrait un SSO (OIDC) et des rôles portés par l'annuaire. Détail, routes de chaque identité et autres limites : `CONTRATS.md`, avenant « authentification des appels au backend ».

## Secrets

Aucun secret réel dans le dépôt ni dans son historique. Les clés qui apparaissent (canaris, fixtures de tests) sont des valeurs fictives d'Orbis Pay. Le contrôle combine gitleaks et un script Python, et tourne avant chaque commit :

```bash
git config core.hooksPath .githooks      # une fois par clone
python3 scripts/scan_secrets.py          # arbre et historique
gitleaks git . --config .gitleaks.toml   # si gitleaks est installé
```

Résultats, périmètre et valeurs fictives autorisées : [docs/SCAN_SECRETS.md](docs/SCAN_SECRETS.md). Le badge en tête de page est à retirer si ce scan cesse de passer.

## Limites connues

- Scénarios et données fictifs. Les noms, les mails, les secrets et les paiements d'Orbis Pay ont été écrits pour la démo.
- Trafic du banc synthétique, agent interne scripté : aucun vrai modèle n'a lu le mail piégé dans les mesures.
- Pas de branchement sur une vraie messagerie : le garde-mail lit une boîte Mailpit locale, pas Outlook ni Gmail. L'inventaire des agents IA lit une configuration factice par défaut.
- Le désarmeur, l'analyseur de mails et l'extension reposent sur des motifs. Une consigne paraphrasée, visible et polie peut passer le désarmeur ; c'est pourquoi la passerelle contrôle aussi l'action (jeton, canaris, envoi externe retenu).
- Le relecteur IA lit des faits structurés, pas le texte brut, mais reste attaquable comme tout modèle. Il peut accorder à tort un geste que les règles laissent ouvert : l'analyste garde le recours, après coup.
- Le brouillon NIS2 est à relire : aucune qualification juridique, aucun envoi. Les correspondances OWASP, ATLAS et ATT&CK n'ont été auditées par personne.
- SQLite et un seul écrivain suffisent à la démo, pas à un grand groupe. Pas d'annuaire d'identités : un jeton par rôle, pas par personne (voir Authentification).
- L'app Mac est signée ad hoc, sans notarisation. Son port 8712 n'a pas d'authentification : un programme local peut y afficher une fausse alerte.

## Documents

[Déroulé de la démo du jury](docs/DEMO_JURY.md), [guide complet de la démo](docs/DEMO.md), [fiche jury](docs/FICHE_JURY.md) et sa [version PDF](docs/FICHE_JURY.pdf), [deck](docs/pitch/dedale-pitch-8-slides.pdf), [mesures](docs/mesures/resultats.md), [contrats entre modules](CONTRATS.md), README de chaque module.
