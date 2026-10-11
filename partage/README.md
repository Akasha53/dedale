# Règles communes des sites louches

L'extension Chrome (`extension/`) et l'app Mac (`app-mac/`) jugent les adresses avec les mêmes règles, rangées dans `regles-sites.json`. L'extension en lit une copie (`extension/regles-sites.json`), car Chrome ne lit que le dossier de l'extension. L'app Mac lit la copie que `construire.sh` range dans `Dedale.app`, ou ce fichier-ci quand elle tourne depuis le dépôt.

Le même algorithme existe deux fois : `extension/comparateur.js` et `app-mac/Sources/Dedale/SitesRegles.swift`. Une modification se fait des deux côtés, puis `verifier.sh` doit passer.

```bash
partage/synchroniser.sh   # recopie les règles dans extension/
partage/verifier.sh       # tests de l'extension, moteur Swift sur le corpus, comparaison des deux
```

## Ce qui est repéré

Le moteur ne lit que l'hôte de l'adresse et ce qui précède un « @ ». Jamais le chemin, les paramètres ni le contenu de la page.

| Catégorie | Exemples | Ce qui déclenche |
|---|---|---|
| `sosie` | `paypa1.com`, `gooogle.com`, `arneli.fr`, `xn--pypal-4ve.com` | même nom sur une autre extension, lettres remplacées par des chiffres ou des caractères d'un autre alphabet (punycode), tiret ajouté ou retiré, une ou deux lettres d'écart |
| `marque_detournee` | `paypal.com.verif-compte.xyz`, `impots-gouv-remboursement.com`, `google-drive.top` | un vrai domaine de la marque placé en sous-domaine, la marque accolée à un mot d'appât, ou la marque sur une extension à risque |
| `arobase` | `http://paypal.com@203.0.113.5/` | ce qui précède « @ » ressemble à un domaine ou nomme une marque |
| `ip_brute` | `http://203.0.113.5/login` | adresse IP publique (les adresses privées et locales restent muettes) |
| `alphabets_melanges` | `xn--mgasin-3nf.com` (« mаgasin », а cyrillique) | un même libellé mêle plusieurs alphabets |
| `adresse_louche` | `a.b.c.d.example-host.com`, `secure-login-verification.xyz` | sous-domaines en chaîne, mots d'appât sur une extension à risque, nom fait de plusieurs mots d'appât |
| `raccourci` | `bit.ly/…`, `tinyurl.com/…` | signalé comme tel, sans alarme : l'adresse d'arrivée est jugée après la redirection |

Chaque alerte porte la marque imitée (ou aucune) et une raison en une phrase, tirée des modèles de `textes.raisons`.

## Le fichier

- `organisation` : le nom et les domaines de l'entreprise protégée (Orbis Pay par défaut). Les règles y sont plus strictes : son nom n'a rien à faire dans un autre domaine. L'extension remplace ces valeurs par celles de ses réglages.
- `marques` : 33 marques visées en France (administrations, banques, transporteurs, Microsoft, Google, Apple, PayPal, Amazon, Netflix, Doctolib…), avec leurs mots et leurs vrais domaines. Une marque connue n'alerte dans un autre domaine qu'avec un second signal : mot d'appât, extension à risque, vrai domaine en sous-domaine. `ecart: 0` coupe l'écart d'une lettre pour un nom trop proche d'un mot courant (Fortuneo et fortune.com).
  Un TLD de marque fermé figure dans `domaines` comme libellé nu (`microsoft`, `google`, `apple`) : tout ce qui finit par `.microsoft`, `.google` ou `.apple` appartient à la marque et passe en confiance, jamais en sosie (`outlook.cloud.microsoft`).
- `domaines_surs` : sites légitimes qui ressemblent à une marque (`paypay.ne.jp`).
- `mots_courants` : mots ordinaires (`cloud`, `mail`, `office`, `login`…) qu'un label peut porter sans imiter une marque. L'écart d'une ou deux lettres sur une marque ne compte pas quand le label n'est que l'un de ces mots, écrit sans chiffre, sans punycode ni alphabet étranger : `cloud` n'imite pas `icloud`. Un déguisement (`cl0ud`, homoglyphe) garde le label suspect, et l'organisation reste jugée strictement.
- `appats`, `extensions_risque`, `raccourcisseurs`, `suffixes_doubles` : listes à plat.
- `confusables`, `sequences`, `chiffres` : le « squelette » d'un nom, ce que l'œil lit une fois les déguisements retirés.
- `seuils` : écarts tolérés, longueur à partir de laquelle un nom se cherche en sous-chaîne, nombre de sous-domaines.
- `textes` : titres de l'alerte, raisons, conseils du coach.

## Le corpus

`corpus-sites.json` sert aux deux côtés. `legitimes` : 133 adresses qui ne doivent rien déclencher (vraies banques, administrations, sites courants, domaines de marque sous TLD fermé comme `outlook.cloud.microsoft`, `orbispay.example`, adresses locales). `louches` : 74 adresses, chacune avec sa catégorie et sa marque attendues. `raccourcis` : 5 liens. `comparaison_seule` : 79 cas limites (Unicode, ports, identifiants, IPv6, entrées illisibles) que les deux moteurs doivent traiter à l'identique.

Mesure du 11 octobre 2026 : 0 alerte sur les 133 légitimes, 74 louches sur 74, et des résultats identiques entre l'extension et l'app sur les 291 adresses. Avant ce correctif, 5 des 133 légitimes alertaient à tort (3,8 %), toutes sur `cloud` pris pour `icloud`.

## Limites

- Une marque n'est protégée que si elle est dans la liste. Une marque absente, ou une imitation qui s'écarte de plus de deux lettres, passe.
- Un domaine officiel d'une marque qui manque à sa liste (une autre extension achetée pour se protéger, comme `doctolib.com`) déclenche une alerte « autre extension ». Le remède est de l'ajouter à `domaines`.
- Une extension à risque seule ne suffit pas (`abc.xyz`, le site d'Alphabet, reste muet). Un faux site sans marque sur une extension ordinaire, avec un seul mot d'appât, passe.
- Seule une vingtaine de suffixes à deux niveaux (`co.uk`, `gouv.fr`, `ne.jp`…) sont connus, faute de la liste complète des suffixes publics.
- Le moteur ne connaît ni l'âge d'un domaine ni sa réputation.
