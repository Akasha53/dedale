# Extension Dédale : sites sosies

Extension Chrome (Manifest V3) qui prévient un salarié d'Orbis Pay avant qu'il n'ouvre un site imitant `orbispay.example`. Elle ne lit que l'adresse de la page : ni son contenu, ni les formulaires, ni ce que la personne tape.

## Installer en mode développeur

1. Ouvrir `chrome://extensions` et activer « Mode développeur ».
2. Cliquer sur « Charger l'extension non empaquetée » et choisir le dossier `extension/`.
3. Régler depuis l'icône, bouton « Réglages » : nom affiché, domaines de confiance (un par ligne, sous-domaines compris), adresse du backend (`http://127.0.0.1:8700` par défaut). Un backend sur une autre machine demande l'accord de Chrome à l'enregistrement.

Pour une démonstration dans un Chrome normal, taper `http://orbispay-verification.example` dans la barre d'adresse : l'avertissement s'affiche sans qu'aucun serveur n'existe. La page d'options teste aussi une adresse sans l'ouvrir.

## Fonctionnement

Une adresse qui ressemble à un domaine de confiance sans en être un ouvre la page d'avertissement à la place du site. Le comparateur (`comparateur.js`) repère six cas : même nom avec une autre extension (`orbispay.com`), lettres d'un autre alphabet ou accents (punycode), chiffres déguisés (`0rbispay`), tiret ajouté ou retiré, une lettre d'écart (deux au-delà de neuf lettres), nom de confiance glissé dans un autre domaine (`orbispay-verification.example`, `orbispay.example.secure-login.com`).

L'avertissement passe avant la page par deux voies. Les adresses qui contiennent le nom de confiance, même déguisé, sont bloquées dans Chrome par une règle `declarativeNetRequest` générée depuis la liste : aucune requête ne part vers le sosie. Les autres cas sont repérés au début de la navigation par `webNavigation`, qui renvoie l'onglet vers l'avertissement.

« Revenir en arrière » ramène à la page précédente et n'envoie rien. « Continuer quand même » ouvre la page, autorise ce domaine jusqu'à la fermeture du navigateur et envoie au backend un événement `avertissement` qui ne porte que le domaine (section « Extension Chrome » de `CONTRATS.md`). Si le backend ne répond pas, la page s'ouvre quand même et la fenêtre de l'icône l'indique.

L'icône affiche le nombre de sites sosies évités : avertissements affichés, moins ceux où la personne a continué.

Permissions : `webNavigation` pour lire l'adresse, `declarativeNetRequest` pour bloquer, `storage`, et l'accès à `127.0.0.1` et `localhost` pour joindre le backend.

## Tester

```bash
cd extension
node --test tests/comparateur.test.js   # 18 tests du comparateur
node tests/bout_en_bout.js              # parcours complet dans Chrome sans fenêtre
```

`bout_en_bout.js` demande Node 22 ou plus, `uv` et Chrome. Il lance sur des ports libres un backend Dédale isolé (`DEDALE_DB` temporaire, jamais le port 8700) et un faux site local, puis Chrome sur un profil temporaire. `--host-resolver-rules` envoie `*.example` vers le faux site, sans toucher à `/etc/hosts`. Chrome stable ignore `--load-extension` depuis la version 137 : le script charge l'extension par le canal CDP `Extensions.loadUnpacked`. La variable `CHROME` choisit un autre binaire, `--captures <dossier>` garde les captures d'écran.

Le script visite un domaine neutre, le vrai domaine et quatre sosies (dont un qui ne résout nulle part), clique sur les deux boutons, coupe le backend, puis vérifie l'incident `humain_phishing`, le contenu exact de l'événement (ni chemin ni paramètres), les compteurs et le badge.

## Limites

- La liste de confiance est statique et saisie à la main. L'extension ne connaît pas la réputation des sites et ne remplace pas la navigation sécurisée de Chrome.
- La détection est une heuristique. Un sosie plus éloigné (deux lettres d'écart sur un nom court, adresse raccourcie, autre marque) passe. Un site légitime qui contient le nom, comme `orbispay-partenaires.fr`, est signalé : la personne le débloque d'un clic pour la session.
- Faute de liste complète des suffixes publics, seule une vingtaine de suffixes à deux niveaux (`co.uk`, `com.au`, `gouv.fr`…) sont reconnus.
- Une lettre d'écart ou un nom en punycode ne sont pas couverts par la règle de blocage : sur un site très rapide, la première requête peut partir et la page commencer à s'afficher avant que l'avertissement la remplace.
- Seul le cadre principal est examiné. Un sosie chargé dans une iframe d'un autre site n'est pas vu.
- Un retour arrière n'est pas envoyé au backend : les « gestes arrêtés » des mesures Dédale ne comptent pas ceux de l'extension.
