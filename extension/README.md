# Extension Dédale : sites louches

Extension Chrome (Manifest V3) qui prévient un salarié d'Orbis Pay avant qu'il n'ouvre un site louche : un sosie d'Orbis Pay ou d'une marque connue, une marque glissée dans un autre domaine, une adresse IP brute, l'astuce « marque@vrai-hôte ». Elle ne lit que l'adresse de la page : ni son contenu, ni les formulaires, ni ce que la personne tape.

Les règles sont communes avec l'app Mac. Elles vivent dans `partage/regles-sites.json` ; `regles-sites.json`, ici, en est la copie que Chrome peut lire (`partage/synchroniser.sh` la refait). Le détail des règles et du corpus de test est dans `partage/README.md`.

## Installer en mode développeur

1. Ouvrir `chrome://extensions` et activer « Mode développeur ».
2. Cliquer sur « Charger l'extension non empaquetée » et choisir le dossier `extension/`.
3. Régler depuis l'icône, bouton « Réglages » : nom affiché, domaines de confiance de l'entreprise (un par ligne, sous-domaines compris), adresse du backend (`http://127.0.0.1:8700` par défaut). Un backend sur une autre machine demande l'accord de Chrome à l'enregistrement.

Pour une démonstration dans un Chrome normal, taper `http://orbispay-verification.example` ou `http://paypal.com.verif-compte.example` dans la barre d'adresse : l'avertissement s'affiche sans qu'aucun serveur n'existe. La page d'options teste aussi une adresse sans l'ouvrir.

## Fonctionnement

Une adresse louche ouvre la page d'avertissement à la place du site. Le titre dit « Ce site imite PayPal. Ce n'est pas le vrai site. » quand une marque est imitée, et « Ce site n'a pas l'air sûr. N'y saisissez rien. » sinon (adresse IP, sous-domaines en chaîne). Une phrase donne la raison ; la ligne « Le vrai site » rappelle le domaine officiel quand il y en a un. « Revenir en arrière » a le focus.

Les domaines de l'entreprise (réglages) sont protégés plus strictement que les marques connues : leur nom n'a rien à faire dans un autre domaine (`orbispay-partenaires.fr` est signalé). Une marque connue n'est signalée dans un autre domaine qu'avec un second signal : un mot d'appât (`paypal-secure-login.com`), une extension à risque (`google-drive.top`) ou un vrai domaine placé en sous-domaine (`paypal.com.verif-compte.xyz`).

L'avertissement passe avant la page par deux voies. Les adresses qui contiennent le nom d'un domaine de l'entreprise, même déguisé, sont bloquées dans Chrome par une règle `declarativeNetRequest` générée depuis la liste : aucune requête ne part vers le sosie. Les autres sites louches sont repérés au début de la navigation par `webNavigation`, qui renvoie l'onglet vers l'avertissement.

« Revenir en arrière » ramène à la page précédente et n'envoie rien. « Continuer quand même » ouvre la page, autorise ce domaine jusqu'à la fermeture du navigateur et envoie au backend un événement `avertissement` qui ne porte que le domaine (section « Extension Chrome » de `CONTRATS.md`). Si le backend ne répond pas, la page s'ouvre quand même et la fenêtre de l'icône l'indique.

Un lien raccourci (`bit.ly`, `tinyurl.com`…) n'ouvre pas d'avertissement : la fenêtre de l'icône le note, et l'adresse d'arrivée est jugée après la redirection.

L'icône affiche le nombre de sites louches évités : avertissements affichés, moins ceux où la personne a continué.

Permissions : `webNavigation` pour lire l'adresse, `declarativeNetRequest` pour bloquer, `storage`, et l'accès à `127.0.0.1` et `localhost` pour joindre le backend.

## Avec l'app Mac

L'app Mac lit elle aussi l'adresse de l'onglet actif de Chrome. Elle laisse la main à l'extension : une adresse louche n'alerte dans l'app qu'au second relevé, et si l'onglet est passé entre-temps sur la page d'avertissement de l'extension, l'app ne fait rien, y compris quand le salarié continue depuis cette page.

## Tester

```bash
cd extension
node --test tests/comparateur.test.js   # 26 tests du moteur, corpus partagé compris
node tests/bout_en_bout.js              # parcours complet dans Chrome sans fenêtre (32 vérifications)
../partage/verifier.sh                  # même corpus passé au moteur Swift de l'app, résultats comparés
```

`bout_en_bout.js` demande Node 22 ou plus, `uv` et Chrome. Il lance sur des ports libres un backend Dédale isolé (`DEDALE_DB` temporaire, jamais le port 8700) et un faux site local, puis Chrome sur un profil temporaire. `--host-resolver-rules` envoie `*.example` vers le faux site, sans toucher à `/etc/hosts`. Chrome stable ignore `--load-extension` depuis la version 137 : le script charge l'extension par le canal CDP `Extensions.loadUnpacked`. La variable `CHROME` choisit un autre binaire, `--captures <dossier>` garde les captures d'écran.

Le script visite un domaine neutre, le vrai domaine et quatre sosies d'Orbis Pay (dont un qui ne résout nulle part), clique sur les deux boutons, coupe le backend, puis vérifie l'incident `humain_phishing`, le contenu exact de l'événement (ni chemin ni paramètres), les compteurs et le badge. Il finit par une marque connue détournée (`paypal.com.verif-compte.example`) et une adresse IP brute.

## Limites

- Une heuristique sur l'adresse seule. Elle ne connaît pas la réputation d'un site et ne remplace pas la navigation sécurisée de Chrome. Les limites des règles communes sont dans `partage/README.md`.
- Un site légitime qui contient le nom de l'entreprise, comme `orbispay-partenaires.fr`, est signalé : la personne le débloque d'un clic pour la session.
- Seuls les sosies des domaines de l'entreprise sont bloqués avant la requête. Pour les autres sites louches, sur un site très rapide, la première requête peut partir et la page commencer à s'afficher avant que l'avertissement la remplace.
- Seul le cadre principal est examiné. Un site louche chargé dans une iframe d'un autre site n'est pas vu.
- Un retour arrière n'est pas envoyé au backend : les « gestes arrêtés » des mesures Dédale ne comptent pas ceux de l'extension.
