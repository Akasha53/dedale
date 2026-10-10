# Garde-mail (`messagerie/`)

De vrais mails arrivent dans une boîte de démo locale. Pour chacun, un analyseur dit s'il est sûrement frauduleux et pourquoi, en une phrase par signal : « Le lien affiche orbispay.example mais mène à orbispay-verification.example. » Les mails sont fictifs (Orbis Pay) et tous les domaines sont en `.example`.

## Lancer

```bash
brew install mailpit                   # une fois
cd messagerie
./demarrer.sh --service                # boîte : web 8716, SMTP 8717 ; service : 8715
uv run python envoyer_demo.py --vider  # vide la boîte et envoie les 12 mails du jeu
curl -s http://127.0.0.1:8715/verdicts | python3 -m json.tool
./demarrer.sh --arreter
```

`./demarrer.sh` seul lance la boîte sans le service, et ne relance rien de ce qui tourne déjà. L'interface de Mailpit (http://127.0.0.1:8716) montre les mails reçus. Le service relève la boîte chaque seconde et pousse chaque nouveau verdict sur `GET /flux` (SSE) et `WS /ws`.

Chaque mail frauduleux part aussi au backend Dédale, à l'adresse `DEDALE_BACKEND` (8700 par défaut). `MESSAGERIE_SIGNALER=0` coupe cet envoi. Pour essayer sur un backend isolé, arrêter d'abord un service déjà lancé (il garde son backend), puis :

```bash
cd backend && DEDALE_DB=/tmp/dedale-essai.db uv run uvicorn app.main:app --port 8790
cd messagerie && DEDALE_BACKEND=http://127.0.0.1:8790 ./demarrer.sh --service
```

Les routes, le format d'un verdict et l'événement envoyé au backend sont décrits dans `CONTRATS.md`, avenant « garde-mail ».

## Le jeu de démo

`uv run python envoyer_demo.py --lister` affiche les cas, `--cas sosie piece_exe` en envoie quelques-uns.

| Cas | Attendu | Ce qu'il montre |
|---|---|---|
| `rh_entretiens` | sûr | mail RH interne, lien vers l'intranet |
| `facture_nuvola` | sûr | facture d'un fournisseur connu, PDF joint |
| `lettre_interne` | sûr | newsletter interne, avec un texte d'aperçu masqué |
| `relance_paiement` | suspect | relance pressante d'un fournisseur inconnu |
| `sosie` | frauduleux | domaine `orbispay-verification.example`, lien qui ment |
| `nom_affiche` | frauduleux | nom affiché « Service Paie Orbis Pay », adresse ailleurs, RIB à changer |
| `lien_menteur` | frauduleux | texte du lien et destination différents, lien avec `@` |
| `piece_exe` | frauduleux | pièce jointe `facture.pdf.exe` |
| `piece_macro` | frauduleux | classeur `.xlsm` à macros qu'il faut « activer » |
| `fraude_president` | frauduleux | la PDG pressée qui demande un virement secret |
| `instruction_blanche` | frauduleux | consigne pour un assistant IA écrite en blanc sur blanc |
| `caracteres_invisibles` | frauduleux | la même consigne en caractères Unicode invisibles |

## Ce que l'analyseur repère

- un domaine sosie d'un domaine de confiance : nom de marque recopié, faute de frappe, caractères qui se ressemblent (0 pour o, cyrillique, punycode), autre extension, faux préfixe ;
- un nom affiché qui se réclame d'Orbis Pay ou d'un dirigeant alors que l'adresse est ailleurs, et des réponses détournées vers une autre adresse ;
- un lien dont le texte annonce un domaine et mène à un autre, un lien avec `@`, un lien vers une adresse IP ;
- une pièce jointe dangereuse : programme déguisé en document, macros, caractère qui inverse l'affichage du nom, programme caché dans une archive ;
- la pression et l'argent : urgence ou secret avec un virement, une demande d'identifiants, un changement de RIB ;
- une consigne cachée pour un assistant IA : texte invisible (blanc sur blanc, police nulle, `display:none`, hors écran), commentaire HTML, caractères invisibles, et la phrase « ignore les instructions précédentes » en français, anglais, espagnol, allemand, italien et portugais ;
- un échec SPF, DKIM ou DMARC noté dans `Authentication-Results`.

## Tests

```bash
uv run --extra dev pytest      # 72 tests, sans réseau ni Mailpit
```

Ils couvrent chaque piège du jeu, l'absence de signal sur les mails légitimes, les variantes de sosies et de textes cachés, et le service : relève, mail désarmé, flux SSE et WebSocket, envoi unique au backend, backend ou boîte absents.

## Limites

- La boîte est une boîte de démo. Mailpit garde ce qu'on lui envoie sur 127.0.0.1, il ne relaie rien et ne reçoit rien de l'extérieur. Rien n'est branché sur une vraie messagerie.
- Les signaux sont des heuristiques. Les mots-clés, les domaines de confiance et les noms des dirigeants sont écrits à la main pour Orbis Pay. Un fraudeur qui évite ces mots passe. Un vrai fournisseur qui relance en pressant sort en « suspect ». Une newsletter qui passe ses liens par un domaine de suivi déclencherait « lien menteur ».
- Il n'y a pas de vrai SPF, DKIM ni DMARC : l'analyseur lit un en-tête `Authentication-Results` simulé, posé par le jeu de démo au nom de `mx.orbispay.example`. Aucune requête DNS, aucune signature vérifiée.
- Aucun lien n'est ouvert ni résolu, aucune pièce jointe n'est lancée. Une archive Office ou ZIP est seulement listée en mémoire. Un test coupe le réseau pendant l'analyse pour le vérifier.
- Les verdicts vivent dans la mémoire du service. Au redémarrage, il réanalyse la boîte et ne renvoie pas au backend un mail que celui-ci connaît déjà.
