# sAIfe pour Mac (démo)

Une application de barre de menus. Elle affiche une pop-up quand un geste à risque se présente : un mail frauduleux arrivé dans la boîte de démo, un fichier à risque qui arrive dans Téléchargements, ou un geste signalé sur le port local. Le salarié choisit Annuler ou Continuer (Mettre de côté ou Garder pour un fichier). Après Annuler, un court coach explique le piège. Un geste critique (virement, export de données clients) attend l'accord d'un analyste du SOC. L'app fait aussi l'inventaire des assistants IA configurés sur le poste et l'envoie à la SOC.

Ce que l'app regarde sur le Mac se limite à trois choses : l'adresse de l'onglet actif de Safari ou de Chrome quand l'un d'eux est au premier plan, les nouveaux fichiers du dossier Téléchargements, et les fichiers de configuration MCP des assistants connus (une configuration factice par défaut). Elle ne lit ni la messagerie du Mac, ni le presse-papiers, ni le clavier, ni l'écran, ni l'historique. Les mails viennent de la boîte de démo locale (`messagerie/`), les autres gestes du simulateur `poste/` ou d'un `curl`. Les autorisations demandées sont l'accès au dossier Téléchargements et le contrôle de Safari et de Chrome, limité à la lecture de l'adresse. Le panneau « Ce que sAIfe regarde sur ce poste » dit tout cela dans l'app, module par module.

![Mail frauduleux](captures/mail.png)

## Apparence

L'app reprend le système visuel de la console SOC : police système, gris partout, une couleur seulement quand elle a un sens (rouge pour le danger, orange pour ce qui attend une décision, vert pour ce qui est réglé), boutons en pilule avec le bouton principal noir et le secondaire en contour, cartes blanches aux coins de 18 à 20 points et au bord fin. Tous ces jetons sont dans `Sources/Dedale/Theme.swift`, avec le nom de la variable CSS de la console en regard. La console n'a qu'un thème clair : les fenêtres et le menu restent clairs quand macOS est en mode sombre. Captures avant et après, à côté de la console : `../captures/app-theme/`.

## Lancer

Il faut macOS 13 ou plus et Swift 5.9 ou plus (Xcode ou les outils en ligne de commande).

```bash
cd app-mac
./construire.sh            # construit Dedale.app
./construire.sh --lancer   # construit puis ouvre l'app
```

L'app s'affiche sous le nom sAIfe (`CFBundleName`, `CFBundleDisplayName`). Le paquet `Dedale.app`, le binaire, l'identifiant `example.dedale.garde`, les variables `DEDALE_*` et le dossier `~/Library/Application Support/Dedale` gardent l'ancien nom : les changer ferait redemander à macOS toutes les autorisations déjà données.

Un bouclier apparaît dans la barre de menus, sans icône dans le Dock. Pour la démo complète, lancez aussi le backend (`./lancer.sh` à la racine) et la boîte de démo :

```bash
cd messagerie
./demarrer.sh --service                     # Mailpit (8716, SMTP 8717) et service de verdicts (8715)
uv run python envoyer_demo.py --cas sosie   # fait arriver un mail piégé
```

## Le menu

Une seule icône dans la barre de menus, un bouclier dont la forme suit l'état d'ensemble. En tête du menu :

- « Protégé » quand les quatre modules tournent et que le backend répond ; sinon « Protégé, équipe sécurité injoignable », « Protection partielle (3 modules sur 4) » ou « Protection en pause » ([capture](../captures/app-poste/menu-protection-partielle.png)).
- Le compteur : « 3 pièges évités cette semaine ». Chaque Annuler ou Mettre de côté compte, depuis lundi. Les dates restent sur le Mac, dans `~/Library/Application Support/Dedale/pieges-evites.json`.

Puis « Agents IA : 7 serveurs dont 3 à risque » (un clic ouvre l'inventaire), avec un point rouge seulement s'il y a un risque. Enfin « Signaler un mail suspect… », « Fichiers mis de côté », « Ce que sAIfe regarde sur ce poste… », « Tester une alerte » et « Quitter ».

![Menu](../captures/app-poste/menu.png)

L'état de chaque module est un diagnostic, caché au salarié : il ne s'affiche que si la touche Option est pressée à l'ouverture du menu. « Connecté à l'équipe sécurité » (sonde `/api/mesures` toutes les 5 s), « Boîte de démo : 6 mails », « Téléchargements surveillés », « Alertes locales sur le port 8712 » et l'état de la veille des sites. Seule exception : un dossier Téléchargements à autoriser ou introuvable reste visible, en orange, puisqu'il attend une action ([menu normal](../captures/finitions/app-mac/apres/menu.png), [avec Option](../captures/finitions/app-mac/apres/menu-option.png)). Le salarié lit « l'équipe sécurité » partout où l'app parlait de la SOC.

## Mails frauduleux

L'app s'abonne au flux `GET /flux` de `messagerie/` et relève `GET /verdicts` toutes les 3 s en secours. Chaque nouveau mail jugé `frauduleux` ouvre la pop-up : le titre de l'alerte, l'objet et l'adresse de l'expéditeur, puis une ou deux raisons en clair. Un mail `suspect` n'ouvre rien. Les mails déjà là au lancement de l'app ne rejouent pas d'alerte.

« Voir le mail » ouvre un aperçu désarmé à côté de la pop-up ([capture](captures/apercu-mail.png)). Le corps est du texte brut : aucun HTML n'est rendu, rien ne se charge, les liens sont réécrits (`hxxps://`, `[.]`) et ne se cliquent pas. Sous le corps, l'aperçu montre où mènent vraiment les liens, les pièces jointes (jamais ouvertes) et le texte caché que l'analyseur a relevé.

Le choix du salarié part au backend dans la session `mail-<id>`, celle où `messagerie/` a déjà déposé le mail reçu. Un Continuer ouvre donc l'incident `humain_phishing` avec le mail en contexte.

Sans la boîte de démo, rien ne casse : le menu affiche « Boîte de démo hors ligne » ([capture](captures/menu-hors-ligne.png)) et l'app réessaie.

## Le coach, après Annuler

La pop-up devient une explication de trois lignes : « C'est annulé. », le piège, et comment le repérer la prochaine fois. « Compris » la ferme, sinon elle part seule au bout de 30 s pour ne pas bloquer les alertes suivantes.

![Coach](captures/mail-coach.png)

Le piège vient de la première raison du verdict, ou du `detail` de l'alerte. Le repère vient du code du signal le plus lourd (`lien_menteur`, `sosie_domaine`, `urgence_argent`…), sinon d'un petit catalogue par catégorie dans `Coach.swift` ([capture hors mail](captures/popup-coach.png)).

## Signaler un mail suspect

Le sous-menu liste les 8 derniers mails de la boîte ([capture](captures/menu-signaler.png)). Un clic envoie un événement `signalement` au backend, avec le mail désarmé en `document_source`, puis affiche « Merci, la SOC est prévenue. » ([capture](captures/signalement.png)). Le mail signalé prend une coche. Le format est dans `CONTRATS.md`, section « app Mac, signalement et quatre yeux ».

## Les quatre yeux

Une alerte de gravité `critique` ne passe pas sur le seul Continuer. C'est le cas d'un mail qui réclame un virement (le verdict porte `geste: virement`), d'un mail que l'analyseur juge critique, ou d'un `POST /avertir` avec `"gravite": "critique"`. La note sous les boutons le dit avant le choix.

Après Continuer, la pop-up passe en « Demande envoyée à la SOC… » avec le temps restant. L'app ouvre l'incident au backend et attend la décision de l'analyste dans la console : « Classer sans suite » (`ignorer`) accorde le geste, « Clore le dossier » (`clore`) le refuse. Sans décision en 90 s, ou si le backend est injoignable, le geste est refusé. L'issue entre dans la boîte noire de l'incident.

| En attente | Accordé | Refusé | Sans réponse |
|---|---|---|---|
| ![](captures/virement-attente.png) | ![](captures/virement-accorde.png) | ![](captures/export-clients-refuse.png) | ![](captures/quatre-yeux-expire.png) |

## Téléchargements

L'app surveille le premier niveau de `~/Downloads` (FSEvents). Les fichiers déjà là au lancement ne déclenchent rien ; un nouveau fichier est jugé quand sa taille ne bouge plus. La règle lit le nom, l'attribut de quarantaine posé par le navigateur ou Mail (dont seul le domaine est gardé) et la structure du fichier : en-tête, table des matières d'une archive ZIP. Elle ne lit jamais le texte du fichier. Une pop-up s'ouvre pour :

- une double extension (`facture.pdf.app`) ou un nom retourné par un caractère invisible, d'où qu'il vienne ;
- une application, un script, une image disque (`.dmg`, `.iso`), un installeur (`.pkg`) ou un raccourci (`.webloc`, `.url`) reçu par mail, par une messagerie, par AirDrop, ou téléchargé depuis un site hors des domaines connus ;
- un document Office avec macros (`.docm`, ou un `.docx` qui cache un `vbaProject.bin`) ou une archive protégée par mot de passe, venus de l'extérieur.

| Double extension | Macros, gardé | Archive chiffrée, mise de côté |
|---|---|---|
| ![](../captures/app-poste/telechargement-application.png) | ![](../captures/app-poste/telechargement-document-macros-garde.png) | ![](../captures/app-poste/telechargement-archive-chiffree-mis-de-cote.png) |

« Mettre de côté » déplace le fichier dans `~/Downloads/sAIfe - mis de côté/`. Le sous-menu « Fichiers mis de côté » le remet à sa place ([capture](../captures/app-poste/menu-mis-de-cote.png)). Un fichier rangé avant le changement de nom, dans `Dédale - mis de côté/`, se remet en place de la même façon : le journal local garde son chemin complet. « Garder » le laisse où il est. Le choix part à la SOC avec le type du fichier, les motifs, le domaine d'origine et l'empreinte SHA-256, jamais son nom ni son contenu (format dans `CONTRATS.md`, avenant « app Mac, poste »). Garder ouvre un incident `humain_phishing`, comme un Continuer.

Pour la démo, un script dépose trois faux téléchargements inoffensifs, avec une provenance simulée : un paquet `Facture-octobre.pdf.app` sans programme, un `Releve-de-compte.docm` au projet VBA vide reçu « par mail », une archive `Photos-seminaire.zip` chiffrée.

```bash
./demo/deposer_telechargements.sh                       # dans ~/Downloads (ou $DEDALE_TELECHARGEMENTS)
./demo/deposer_telechargements.sh --dossier /tmp/essai  # ailleurs
./demo/deposer_telechargements.sh --nettoyer            # retire les trois fichiers, mis de côté compris (ancien dossier aussi)
```

Au premier lancement de `Dedale.app`, macOS demande l'accès au dossier Téléchargements. Sans cet accord, le menu affiche « Téléchargements : accès à autoriser » et l'app réessaie toutes les 10 s. La signature ad hoc change à chaque construction : macOS peut redemander l'accord après `./construire.sh`.

## Agents IA du poste

L'app lit les fichiers de configuration MCP des assistants connus : Claude Desktop, Claude Code, Cursor, VS Code, Windsurf, Cline, Zed, Gemini CLI, Codex et LM Studio. De chaque serveur, elle n'extrait que le nom, la commande de lancement, ses arguments passés au filtre des secrets et l'hôte d'une URL distante. Les variables d'environnement, les en-têtes et toute autre clé ne sont jamais extraits. Elle en déduit un type (fichiers, shell, mail, navigateur, réseau) et marque les droits risqués : le shell, les mails, tout le disque.

![Agents IA](../captures/app-poste/agents-ia.png)

À la SOC part, pour chaque serveur, le client, le nom, les types, les droits risqués et le transport (`POST /api/agents/poste`, toutes les 5 minutes). Les serveurs apparaissent ensuite dans `GET /api/agents`, `contexte: "poste"`.

Par défaut l'app lit la configuration factice de `demo/agents-factices` (copiée dans `Dedale.app` par `construire.sh`) : sept serveurs sur un poste fictif de la Finance. `DEDALE_DEMO_AGENTS_DIR` pointe vers un autre dossier factice. La vraie configuration du Mac n'est lue qu'avec `DEDALE_AGENTS_REEL=1`, et aucun bouton de l'app ne l'active : un clic pendant une démo ne peut pas l'afficher.

## Sites louches

Quand Safari ou Chrome est au premier plan, et seulement à ce moment-là, l'app lit par AppleScript l'adresse de l'onglet actif, environ chaque seconde. Elle la juge sur le poste avec les règles communes à l'extension Chrome (`partage/regles-sites.json`, détail dans `partage/README.md`) : sosie d'Orbis Pay ou d'une des 33 marques visées en France, marque glissée dans un autre domaine, astuce « @ », adresse IP publique, alphabets mêlés, sous-domaines en chaîne. Un lien raccourci donne une bulle discrète, sans alarme.

Une adresse louche ouvre la pop-up habituelle, avec « Revenir en arrière » et « Continuer quand même ». Revenir en arrière ramène Chrome à la page précédente (l'onglet se ferme s'il n'a pas d'historique). Safari n'a pas de commande de retour : l'app recharge la dernière page sûre vue dans l'onglet, ou ferme l'onglet. Le coach suit, et le compteur de pièges évités monte. Rien ne part à la SOC. Continuer quand même envoie le domaine et la catégorie, sous la forme de l'extension (`contexte: "navigation"`, session `navigateur-` et 8 caractères), et l'app ne réavertit plus pour ce domaine jusqu'à sa fermeture. Ni le chemin, ni les paramètres, ni le contenu des pages, ni l'historique.

| Sosie en punycode | Marque en sous-domaine | Après Continuer | Coach après un retour |
|---|---|---|---|
| ![](../captures/sites-louches/site-punycode-etranger.png) | ![](../captures/sites-louches/site-marque-sous-domaine.png) | ![](../captures/sites-louches/site-marque-sous-domaine-continuer.png) | ![](../captures/sites-louches/site-ip-brute-coach.png) |

Dans Chrome, l'app laisse la main à l'extension : une adresse louche n'y alerte qu'au second relevé, et si l'onglet est passé entre-temps sur la page d'avertissement de l'extension, l'app ne fait rien, même quand le salarié continue depuis cette page.

La première lecture fait poser une question par macOS : « sAIfe souhaite contrôler Safari » (ou Chrome), avec la phrase de `NSAppleEventsUsageDescription`. Un refus se voit dans le menu (« Sites : autorisez sAIfe pour Safari ») et se corrige dans Réglages Système, Confidentialité et sécurité, Automatisation. L'app est signée ad hoc : une reconstruction peut faire reposer la question.

Le moteur Swift (`Sources/Dedale/SitesRegles.swift`) rend les mêmes résultats que celui de l'extension sur le corpus partagé : `../partage/verifier.sh` le compile à part avec `swiftc` et compare les deux, adresse par adresse.

Essai réel, contre un backend isolé : `DEDALE_SITES_ESSAI` ouvre une nouvelle fenêtre Safari, y charge chaque adresse de la liste à son tour, puis la referme. Les autres fenêtres ne sont pas touchées.

```bash
open -n -a Dedale.app --env DEDALE_BACKEND=http://127.0.0.1:8781 --env DEDALE_PORT_LOCAL=8792 \
  --env DEDALE_ETAT=/tmp/dedale-etat --env DEDALE_CAPTURE=/tmp/captures --env DEDALE_CLIC_AUTO=annuler,compris \
  --env "DEDALE_SITES_ESSAI=https://www.service-public.fr/ http://orbispay-verification.example/ http://203.0.113.5/login"
```

`open` plutôt que le binaire seul : lancé depuis un terminal, le binaire ferait demander l'autorisation au nom du terminal. Une seule instance de `Dedale.app` tourne à la fois : quitter celle de la démo avant.

## Ce que sAIfe regarde sur ce poste

Le panneau liste les quatre modules (Mails, Sites, Téléchargements, Agents IA), ce que chacun lit, ce qui part à la SOC, avec un interrupteur par module. Un module coupé ne lit plus rien et n'envoie plus rien ; le réglage reste sur le Mac (`modules.json`). En bas, ce que l'app ne lit jamais : le presse-papiers, les frappes au clavier, les captures d'écran, le contenu des pages, l'historique de navigation. Les textes viennent de `Sources/Dedale/ModulesPoste.swift`, et la section « Vie privée » de la landing les reprend.

| Tout est allumé | Agents IA coupé |
|---|---|
| ![](../captures/app-poste/transparence.png) | ![](../captures/app-poste/transparence-agents-coupe.png) |

## Tests unitaires

Les règles sans interface (téléchargements, provenance, empreinte, inventaire MCP, filtre des secrets) vivent dans la cible `DedaleNoyau` :

```bash
swift test
```

Un test écrit une fausse configuration où le même jeton se trouve dans une variable d'environnement, un argument, une URL, un en-tête et un nom de serveur, puis vérifie qu'il n'apparaît ni dans l'inventaire, ni dans le corps envoyé à la SOC.

## Tester sans la boîte de démo

```bash
curl -X POST 127.0.0.1:8712/avertir -d '{
  "categorie": "phishing",
  "message": "Ce mail est sûrement frauduleux.",
  "detail": "Il se présente comme Orbis Pay, mais le lien mène vers orbispay-connexion.example.",
  "session_id": "poste-mac-demo-0001"
}'
# {"id":"…","session_id":"poste-mac-demo-0001","statut":"affichee"}

# Un geste critique, qui attend l'accord de la SOC :
curl -X POST 127.0.0.1:8712/avertir -d '{
  "categorie": "mail_externe", "geste": "export_clients", "gravite": "critique",
  "message": "Export de 12 400 fiches clients vers une adresse perso.",
  "session_id": "poste-mac-camille"
}'
```

`categorie` vaut `phishing`, `secret`, `mail_externe`, `upload_ia` ou `intrusion_physique`, et `message` est obligatoire. Le reste est facultatif : `detail`, `session_id` (`poste-mac-demo` par défaut), `geste` (`virement` ou `export_clients`, change le libellé et le conseil du coach), ainsi que `gravite`, `cible` et `lien`, transmis au backend. `GET /etat` renvoie l'état de l'app (SOC, boîte de démo, alerte affichée, file, quatre yeux en attente, pièges évités). Les alertes s'affichent une par une, dix au plus en attente.

L'événement envoyé suit `CONTRATS.md`, avenant « humain » : `source: humain`, `surface: poste`, `type: avertissement`, `details.categorie`, `details.choix`, et `details.message` qui porte le texte de la pop-up.

## Variables

| Variable | Effet |
|---|---|
| `DEDALE_BACKEND` | adresse du backend, `http://127.0.0.1:8700` par défaut |
| `DEDALE_MESSAGERIE` | adresse du service de verdicts, `http://127.0.0.1:8715` par défaut |
| `DEDALE_PORT_LOCAL` | port des alertes locales, 8712 par défaut |
| `DEDALE_QUATRE_YEUX_DELAI` | secondes d'attente de la décision du SOC, 90 par défaut (5 à 600) |
| `DEDALE_MAILS_AU_DEMARRAGE` | `alerter` rejoue les mails frauduleux déjà présents au lancement |
| `DEDALE_ETAT` | dossier du compteur de pièges évités |
| `DEDALE_CLIC_AUTO` | boutons à presser seuls, dans l'ordre, séparés par des virgules : `voir`, `annuler`, `continuer`, `compris`. Chaque clic passe par le vrai bouton (`performClick`) |
| `DEDALE_CLIC_DELAI` | délai avant chaque clic automatique, 2 s par défaut |
| `DEDALE_SIGNALER_AUTO` | identifiant d'un mail (ou `premier`) à signaler une fois, par le même chemin qu'un clic dans le menu |
| `DEDALE_CAPTURE` | dossier où l'app écrit un PNG de chaque état de ses fenêtres et un rendu de son menu, normal et avec Option (`menu-option.png`). Les pop-ups passent alors devant sans prendre le clavier |
| `DEDALE_TELECHARGEMENTS` | dossier surveillé, `~/Downloads` par défaut |
| `DEDALE_DOMAINES_CONNUS` | domaines d'où un programme peut venir sans pop-up, en plus de `orbispay.example`, `apple.com`, `microsoft.com`, `mozilla.org` et `google.com` (virgules) |
| `DEDALE_DEMO_AGENTS_DIR` | dossier factice qui reproduit un dossier personnel, lu par le module Agents IA |
| `DEDALE_AGENTS_REEL` | `1` : lit la vraie configuration MCP du Mac (jamais en démo) |
| `DEDALE_MODULES_COUPES` | modules coupés au lancement : `mails`, `sites`, `telechargements`, `agents` |
| `DEDALE_TELECHARGEMENT_AUTO` | choix à presser seuls, un par pop-up de téléchargement : `mettre_de_cote`, `garder` |
| `DEDALE_REMETTRE_AUTO` | secondes avant de remettre seul à sa place le premier fichier mis de côté, par le sous-menu |
| `DEDALE_OUVRIR` | panneaux à ouvrir au lancement, quatre secondes chacun : `transparence`, `agents` |
| `DEDALE_BASCULER_AUTO` | module dont l'interrupteur est basculé dans le panneau de transparence ouvert par `DEDALE_OUVRIR` |
| `DEDALE_SITES` | `off` coupe la veille des sites (sinon, l'interrupteur « Sites » du panneau) |
| `DEDALE_REGLES_SITES` | fichier de règles des sites à la place de celui rangé dans `Dedale.app` |
| `DEDALE_SITES_ESSAI` | adresses à ouvrir dans une nouvelle fenêtre Safari, séparées par des espaces (essai réel) |
| `DEDALE_SITES_SIMULE` | adresses passées au moteur des sites comme si Safari les affichait, sans lire ni piloter de navigateur, même avec `DEDALE_SITES=off` (captures de la pop-up) |

Elles se passent au binaire : `DEDALE_CLIC_AUTO=voir,annuler,compris ./Dedale.app/Contents/MacOS/Dedale`.

## Vérifier sans toucher à la démo

Les captures de `captures/` viennent de l'app elle-même, contre un backend isolé et une boîte de démo à part :

```bash
# backend sur une base jetable, port 8781
cd backend && DEDALE_DB=/tmp/dedale-test.db DEDALE_LLM=off uv run uvicorn app.main:app --port 8781
# Mailpit et service de verdicts sur 8786, 8787 et 8785
mailpit --listen 127.0.0.1:8786 --smtp 127.0.0.1:8787 --database /tmp/mailpit-test.db
cd messagerie && MESSAGERIE_MAILPIT=http://127.0.0.1:8786 DEDALE_BACKEND=http://127.0.0.1:8781 \
  uv run uvicorn service:app --port 8785
# l'app, sur un autre port local que l'instance de démo
cd app-mac && swift build -c release && DEDALE_BACKEND=http://127.0.0.1:8781 \
  DEDALE_MESSAGERIE=http://127.0.0.1:8785 DEDALE_PORT_LOCAL=8792 DEDALE_ETAT=/tmp/dedale-etat \
  DEDALE_CAPTURE=captures DEDALE_CLIC_AUTO=voir,annuler,compris .build/release/Dedale
# un mail piégé arrive
cd messagerie && uv run python envoyer_demo.py --port 8787 --cas lien_menteur
```

Pour les modules du poste, les captures de `captures/app-poste/` viennent du même binaire, contre un backend isolé sur le port 8795, sans boîte de démo, avec une copie de la configuration factice où un faux jeton a été ajouté :

```bash
DEDALE_BACKEND=http://127.0.0.1:8795 DEDALE_MESSAGERIE=http://127.0.0.1:9 DEDALE_PORT_LOCAL=8796 \
  DEDALE_ETAT=/tmp/essai/etat DEDALE_TELECHARGEMENTS=/tmp/essai/Downloads DEDALE_DEMO_AGENTS_DIR=/tmp/essai/agents \
  DEDALE_CAPTURE=../captures/app-poste DEDALE_OUVRIR=transparence,agents DEDALE_REMETTRE_AUTO=5 \
  DEDALE_TELECHARGEMENT_AUTO=mettre_de_cote,garder,mettre_de_cote .build/release/Dedale
./demo/deposer_telechargements.sh --dossier /tmp/essai/Downloads
```

Résultat de cet essai : trois pop-ups, deux fichiers mis de côté (dont un remis à sa place par le sous-menu), un fichier gardé, donc un seul incident `humain_phishing` ; l'inventaire de sept serveurs reçu par le backend ; et le faux jeton absent du journal de l'app, de la base, du fichier d'inventaire et des réponses de l'API.

Lancé depuis `.build/release/`, le binaire n'a pas d'identifiant de paquet : il tourne à côté d'une instance de `Dedale.app` déjà ouverte. Pour les quatre yeux, prendre la décision par `POST /api/incidents/{id}/decision` sur le backend isolé.

## Limites

- C'est une démo. Hors adresse de l'onglet actif, Téléchargements et configuration MCP, rien n'est observé sur le Mac, et Annuler ou un refus du SOC ne bloquent rien, puisque le geste est simulé. Un fichier gardé reste ouvrable : l'app prévient, elle ne bloque pas.
- La règle des téléchargements juge le nom, la provenance et la structure. Elle ne reconnaît pas un programme malveillant caché dans un PDF ordinaire ni une archive 7z ou RAR chiffrée.
- Le port local n'écoute que sur 127.0.0.1. Il refuse les requêtes qui portent un en-tête `Origin` ou `Sec-Fetch-*`, ainsi que tout hôte autre que 127.0.0.1 ou localhost : une page web ne peut pas afficher de fausse alerte. Un programme local le peut, faute d'authentification.
- Sans backend, la pop-up s'affiche quand même et l'app tient, mais l'événement est perdu : il n'y a pas de file de renvoi. Un geste critique est alors refusé.
- Une décision du SOC qui arrive après le délai des quatre yeux ne change plus rien sur le poste. Dans `/api/mesures`, la demande compte comme un geste passé outre, même refusée.
- Entrée et Échap valent Annuler, une seconde après l'apparition seulement, pour qu'une frappe en cours dans une autre fenêtre ne ferme pas l'alerte. Dans le coach, ils valent Compris.
- Les PNG sont rendus par l'app, posés sur une toile gris clair. Le menu est redessiné à partir de ses lignes, ce n'est pas une capture d'écran du système.
- L'app est signée ad hoc. Copiée sur un autre Mac, elle s'ouvre par clic droit, Ouvrir.
- Sites : l'app réagit après coup, jusqu'à une seconde après l'arrivée de l'adresse dans l'onglet (deux relevés dans Chrome). La page a le temps de commencer à se charger, contrairement aux sosies d'Orbis Pay que l'extension bloque avant la requête. Seuls Safari et Chrome sont lus, et seulement la fenêtre de devant.
- Sites : le retour arrière de Safari recharge la dernière page sûre vue dans l'onglet, ce n'est pas un vrai retour dans l'historique. Sans page connue, l'onglet se ferme.
