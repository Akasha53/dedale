# Relecture design de sAIfe

10 octobre 2026, 23 h. Relecture de la landing, de la console, de la pop-up de démo (`poste/demo/popup.html`) et de l'app Mac (captures de `captures/app-theme/apres/` et `Theme.swift`).

Grille de lecture : les goûts de Guilhem. Référence chatgpt.com, presque tout en gris, une couleur seulement quand elle porte un sens, police du système, pilules pour les boutons et les champs, 16 à 24 px pour les cartes, pas d'étiquettes en capitales espacées, pas de monospace décoratif, thème clair partout.

## Méthode

- Base neuve sur un backend isolé (port 18870), console Vite à part (18871), scénario `orbis.demo --scenario jury`, journée simulée du poste, puis un incident agent laissé ouvert pour la décision dans la console.
- Chrome sans interface, profil temporaire. Chaque écran est pris à 1440 et 390 px. Les captures « avant » sont dans `captures/design-audit/avant/`, les détails élément par élément dans `captures/design-audit/avant/details/`.
- Un script relève les styles calculés de chaque élément visible (police, taille, graisse, couleur, rayon, boutons). Les chiffres ci-dessous en viennent.
- Aucune page ne déborde à 390 px : la largeur défilable est égale à la largeur de l'écran sur les 22 captures.

Références consultées :

- Vercel Geist, couleurs (vercel.com/geist/colors) : les gris 1 à 3 pour les fonds (repos, survol, actif), 4 à 6 pour les bords, 9 pour le texte secondaire, 10 pour le texte principal. Repris pour l'échelle de gris des jetons.
- Apple HIG, « The menu bar » : un menu, pas une fenêtre, au clic sur l'icône de la barre de menus, et une icône en noir et transparent que le système recolore. Repris pour les remarques sur le menu de l'app Mac.
- chatgpt.com : la page publique renvoie un écran de vérification à un Chrome sans interface, je n'ai donc pas pu relever ses styles ce soir. Les valeurs déjà reprises dans la console (texte `#0d0d0d`, secondaire `#5d5d5d`, fonds `#f9f9f9` et `#f4f4f4`, police `ui-sans-serif`) sont gardées telles quelles.

## Ce qui ne colle pas d'une surface à l'autre

| Sujet | Console | Landing | Pop-up de démo | App Mac |
|---|---|---|---|---|
| Accent | noir `#0d0d0d` | cyan `#0e7490` (surtitres, icônes, liens) | cyan `#0e7490` et `#22d3ee` | noir |
| Rouge | `#c4262e` | `#b42318` | `#b42318` | aligné sur la console |
| Vert | `#0f7b55` | `#15803d` | `#15803d` | aligné sur la console |
| Gris faible | `#737373` | `#6b6b6b` | `#6b6b6b` | aligné sur la console |
| Police | `ui-sans-serif, -apple-system…` | `-apple-system, "SF Pro Text"…` | idem landing | système |
| Monospace | 114 textes : heures, « MITRE ATT&CK », « en attente depuis… » | 5 textes : rangée OWASP / ATLAS / ATT&CK | 3 textes, adresses de sites (légitime) | aucun |
| Tailles de texte | 29 couples taille/graisse, de 10 à 36 px, par demi-pixel | 25 couples | 23 couples | — |
| Rayons de carte | 20, 16, 14, 12, 18 et 22 px sur le même écran | 28, 30, 22, 24, 20, 16 px | 28, 22, 20, 18 px | 18 à 20 px |
| Bouton principal | pilule noire, ou pilule rouge pleine pour « Couper » | pilule noire | rectangle cyan rayon 12 px pour l'alerte Mac, pilule noire pour l'extension | pilule noire |

La console et l'app Mac sont passées au noir ce soir ; la landing et la pop-up de démo sont restées sur le cyan de l'ancienne charte. Le nouveau logo (deux crochets noirs autour d'un disque) tranche la question : l'accent de marque est l'encre noire, la couleur reste réservée au sens.

## Défauts par écran

P0 : cassé ou laid au premier regard. P1 : incohérent. P2 : finition. La colonne « qui » dit qui peut corriger ce soir sans marcher sur un autre agent.

### Console, temps réel (agents IA)

Capture : `avant/console-temps-reel-agents-1440.png`, `avant/console-temps-reel-agents-390.png`.

| | Défaut | Qui |
|---|---|---|
| P0 | Cartes d'agent : le titre passe sur deux ou trois lignes parce que la pastille d'état lui prend la moitié de la largeur ; « Direction des opérations » se replie dans une colonne étroite. Les quatre cartes commencent leur description à des hauteurs différentes. | agent Inventaire (`agent/Inventaire.tsx`) |
| P0 | « Droits en trop » : cinq puces rouges par carte, dont certaines sur deux lignes (« ouvrir le coffre des clés secrètes ») ; une pilule cassée en deux ressemble à une erreur. C'est le même défaut que le vert répété des « Postes » : la couleur est partout, donc elle ne dit plus rien. | agent Inventaire |
| P1 | Quatre cartes dans une grille de trois : la quatrième reste seule sur sa ligne. | agent Inventaire |
| P1 | Pied de carte : quatre styles de bouton dans la même rangée (pilule « Risque élevé » teintée, pilule « Pourquoi ? » en contour, texte nu « Écrire une règle », pilule orange « Décider »). | agent Inventaire |
| P1 | À 390 px, trois niveaux d'enveloppe (panneau, carte, puits gris) : le texte utile tient dans 290 px sur 390. | agent Inventaire |
| P1 | « Ce que font les agents » : heures en monospace, statut coloré trois fois par ligne (point, mot, couleur du mot). | agent listes, sauf la police (jetons) |

### Console, incident d'un agent

Capture : `avant/console-incident-ouvert-1440.png`, détails dans `avant/details/incident-agent-*.png`.

| | Défaut | Qui |
|---|---|---|
| P0 | Panneau « Votre décision » : titre de 17 px en orange sur deux lignes, avec le point d'état qui flotte entre les deux lignes au lieu de s'aligner sur la première ; « depuis 11 min 47 s » en orange en dessous. Trois signaux orange empilés pour une seule information. | moi |
| P1 | En-tête : trois pastilles de trois couleurs côte à côte (« Haute » rouge, « À décider » orange, « Journal intact » vert). | moi |
| P1 | Monospace décoratif : heures de la boîte noire, « repéré à 23:02:21 », « en attente depuis 4 min 41 s » en monospace orange. | moi (jetons) |
| P1 | À 390 px, le bloc « Repéré / Signalé au SOC / Décision » passe sur deux colonnes, avec un filet au-dessus de deux cases sur trois. | moi |
| P1 | « Pourquoi ce niveau de certitude » garde le triangle natif du navigateur. | moi |
| P1 | Deux certitudes différentes à l'écran : « Sûr à 95 % » dans le résumé, « sûr à 85 % » dans le pré-tri du relecteur. Un juré le verra. | backend / relecteur, à trancher |
| P2 | Boîte noire : l'étape « Résultat » n'a pas d'heure, son chevron se colle au libellé au lieu de rester dans la colonne des autres chevrons. | moi |

### Console, incident d'un salarié

Capture : `avant/console-incidents-salaries-1440.png`, `avant/details/incident-salarie-*.png`.

| | Défaut | Qui |
|---|---|---|
| P1 | « Le message affiché par sAIfe » : filet orange de 3 px à gauche d'une carte arrondie ; le filet suit l'arrondi et se tord aux coins. | moi |
| P1 | Même titre de décision orange que pour un agent. | moi |
| P1 | Deux panneaux de décision, deux langages : pilules à pastille d'icône pour l'agent, pilules nues pour le salarié. | à harmoniser plus tard, pas ce soir |

### Console, mesures

Capture : `avant/console-mesures-1440.png`.

| | Défaut | Qui |
|---|---|---|
| P1 | Accord en nombre faux : « 1 agents · 1 salariés ». | moi |
| P2 | Dernière rangée : deux cartes de largeurs différentes sous une grille de quatre colonnes égales. | moi |

### Console, partout

| | Défaut | Qui |
|---|---|---|
| P1 | 29 couples taille/graisse, dont 10 et 10,5 px (références MITRE) : trop petit et trop de marches. | moi (jetons) |
| P1 | « MITRE ATT&CK » en monospace 10 px espacé de 0,06 em : c'est l'étiquette en capitales espacées que Guilhem refuse, sans les capitales. | moi |
| P2 | « Analyste : à indiquer » en orange dans l'en-tête de chaque écran. | moi |
| P2 | À 390 px, l'en-tête (titre, phrase, pastille analyste) prend 340 px de haut avant le premier contenu. | moi |

### Landing

Capture : `avant/landing-1440.png`, `avant/landing-390.png`, détails `avant/details/landing-*.png`.

| | Défaut | Qui |
|---|---|---|
| P1 | Surtitres, icônes de la section Exporter et liens en cyan, alors que la console et l'app Mac sont passées au noir. | moi |
| P1 | Captures anciennes : l'alerte Mac de la vitrine et de l'étape 1 montre encore le bouton « Annuler » cyan à petit rayon ; la console de la vitrine montre des heures en monospace et des noms d'agents (« Assistant support ») qui ne sont plus ceux du scénario jury. | moi pour l'alerte Mac, la console après le passage des autres agents |
| P1 | Rangée OWASP / ATLAS / ATT&CK / NIST : « Détecter · Répondre » et « exports vers un SIEM » en monospace. | moi |
| P2 | Grille « Ce qui tourne dans le prototype » : trois rangées, trois coupures de colonne différentes (63 %, 47 %, 55 %) ; les gouttières ne s'alignent jamais. | moi |
| P2 | Titre « Deux cibles. Une vigie. » serré à −0,05 em : les lettres se touchent à 96 px. | moi, l'en-tête reste à l'agent logo |

### Pop-up de démo (`poste/demo/popup.html`)

Capture : `avant/popup-1440.png`, `avant/details/popup-scene-mail-*.png`.

| | Défaut | Qui |
|---|---|---|
| P0 | L'alerte Mac reproduite dans la page a des boutons rectangulaires de 12 px, « Annuler » en cyan plein. Plus bas sur la même page, l'avertissement de l'extension a une pilule noire pour le bon choix. La vraie app Mac affiche depuis 23 h une pilule noire. La page montre donc une alerte qui n'existe plus, avec un bouton qui a l'air natif. | moi (`popup.html` et son générateur `poste/garde/popup.py`) |
| P1 | Pastilles, liens et icône d'alerte en cyan. | moi |

### App Mac (lecture seule, captures de `captures/app-theme/apres/`)

| | Défaut | Qui |
|---|---|---|
| P1 | Menu : trois points verts et un bouclier vert pour dire « tout va bien ». Un seul suffit, les autres lignes peuvent rester grises ; le rouge des agents à risque ressortira mieux. | agent app Mac (`Interface.swift`) |
| P1 | Menu : « Alertes locales sur le port 8832 » et « Sites : veille coupée (DEDALE_SITES=off) » sont des messages de développeur montrés au salarié. | agent app Mac |
| P1 | « Connecté à la SOC » : la console et la landing disent « le SOC ». | agent app Mac |
| P2 | Le guide Apple veut une icône de barre de menus en noir et transparent, que le système recolore ; à vérifier quand le logo à crochets arrive. | agent logo |

## Jetons proposés

Un seul fichier, `design/jetons.css`, chargé par la console et la landing (et lu à la main par `Theme.swift` pour l'app Mac).

Couleurs. Une échelle de gris neutre, sans teinte bleue, et trois couleurs de sens.

| Jeton | Valeur | Usage |
|---|---|---|
| `--gris-0` | `#ffffff` | fond de page, cartes |
| `--gris-50` | `#f9f9f9` | puits, fond de section |
| `--gris-100` | `#f4f4f4` | pastille neutre, survol |
| `--gris-150` | `#ececec` | actif, piste de barre |
| `--gris-200` | `#e5e5e5` | bord |
| `--gris-300` | `#d4d4d4` | bord fort, contour de bouton |
| `--gris-500` | `#8f8f8f` | icônes inactives |
| `--gris-600` | `#6b6b6b` | texte faible (5,3:1 sur blanc) |
| `--gris-700` | `#5d5d5d` | texte secondaire |
| `--gris-950` | `#0d0d0d` | texte, bouton principal, logo |
| `--danger` | `#c4262e` | risque, couper |
| `--attente` | `#c2410c` | attend une décision humaine |
| `--regle` | `#0f7b55` | réglé, protégé |

La couleur de sens ne remplit jamais une pastille entière quand un point de 6 px suffit. Un écran ne montre la même couleur qu'à un endroit par bloc.

Rayons : `--rayon-carte` 20 px (16 px à 390), `--rayon-interieur` 16 px pour un puits dans une carte, `--rayon-controle` 9999 px pour boutons, champs, pastilles et onglets. Rien en dessous de 10 px sauf les points.

Espacements, sur une base de 4 : 4, 8, 12, 16, 20, 24, 32, 48, 72.

Typographie : police du système (`ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif`), chiffres tabulaires pour les heures et les compteurs. Le monospace ne sert qu'au code, aux URL et aux empreintes. Échelle : 12, 13, 14, 15, 17, 20, 24, 32 px pour l'interface ; 48, 64 et 88 px pour les titres de la landing. Trois graisses : 400, 500, 600. Interlettrage nul, sauf −0,02 em au-dessus de 20 px et −0,035 em au-dessus de 40 px.

Mouvement : une courbe, `cubic-bezier(0.23, 1, 0.32, 1)`, 160 ms pour un appui (`scale(0.98)`), 200 ms pour un survol.

## Corrigé ce soir

Captures après dans `captures/design-audit/apres/` (écrans entiers) et `captures/design-audit/apres/details/` (élément par élément), mêmes noms que les captures avant.

- Jetons : `design/jetons.css`, chargé par la landing (`<link>`, avec repli si la page sort du dépôt) et par la console (`@import` en tête de `console/src/finitions.css`, que Vite inline à la compilation). Les anciennes variables de la console pointent vers ces jetons.
- Monospace décoratif : 114 textes en monospace dans la console avant, 14 après, tous des adresses ou des noms de fichier. Plus aucun sur la landing.
- Panneau « Votre décision » (P0) : titre noir, point d'état aligné sur la première ligne, « depuis… » en gris. Agent et salarié.
- En-tête d'incident (P1) : pastilles grises, la couleur tient dans un point ; « Journal intact » en gris.
- Temps de réaction à 390 px (P1), triangle natif de « Pourquoi ce niveau de certitude » (P1), filet orange du message salarié (P1), chevron de l'étape « Résultat » (P2), pastille « Analyste » neutre au repos (P2), champ du motif de décision en pilule.
- Références MITRE et OWASP (P1) : ni monospace ni lettres espacées.
- Landing (P1) : plus de cyan, références en police du système, grand titre desserré, cartes « Ce qui tourne » sur le même décalage 7/5. Les cinq captures de console de `landing/img/v2/` sont refaites sur les données du jury, avec le nouveau logo, au même cadrage ; les PNG sources sont dans `captures/design-audit/apres/landing-img/`.
- Pop-up de démo (P0) : l'alerte Mac reproduite prend la pilule noire et le nouveau logo de la vraie app ; plus de cyan ; rouge et vert des jetons. Le générateur `poste/garde/popup.py` produit toujours la même page.
- `index.css` : la règle `.pastille-logo` et les trois `@font-face` (Space Grotesk, IBM Plex Mono) sont retirées ; le build perd 42 ko de polices.
- « Les postes » (retour de Guilhem, 23 h 41) : seuls les postes à traiter restent en ligne. Les postes traités et les postes calmes se replient en « N postes sans rien à traiter », avec « dont 1 dossier traité aujourd'hui » ; dépliés, les traités viennent d'abord, en gris. Sans rien à traiter, une ligne grise « Rien à traiter sur les postes ». Captures dans `captures/design-audit/postes/`. La liste des incidents suivait déjà cette règle.
- Médiation de la passerelle : les incidents « Outil inconnu », « Canal détourné » et « Outil modifié » ont leur titre, leur étiquette et un « Ce qui s'est passé » tiré du constat de la passerelle (outil, serveur MCP, canary masqué, adresse désarmée, règle C-8A61, C-5B27 ou C-3F90). Captures dans `captures/design-audit/mediation/`.

## Ce qui reste aux autres agents

- Agent Inventaire, `console/src/agent/Inventaire.tsx` et ses règles CSS : titre de carte sur toute la largeur avec la pastille d'état en dessous ; « Droits en trop » en texte gris séparé par des virgules, avec un seul point rouge devant le libellé, jamais une pilule sur deux lignes ; un seul style de bouton au pied de la carte ; grille en `repeat(auto-fill, minmax(320px, 1fr))` ; à 390 px, retirer le puits gris intérieur. La capture d'ouverture de la landing (`landing/img/v2/console-temps-reel.webp`) montre ces cartes : à refaire après leur passage.
- Agent listes, « Ce que font les agents » : la couleur sur le point seulement, le mot du statut en gris.
- Agent app Mac, `Interface.swift` : un seul indicateur vert dans le menu, retrait du port et de la variable d'environnement, « le SOC ». Dans l'écran « C'est annulé », la phrase du piège est coupée (« dont le domaine es… »). Les deux images de l'alerte Mac sur la landing (`app-alerte-mail.webp`, `app-coach.webp`) gardent l'ancien carré « D » et le bouton cyan : à refaire depuis `captures/app-theme/logo/` une fois la phrase réparée.
- Backend ou relecteur : la certitude du résumé (95 %) et celle du pré-tri (85 %) se contredisent. Les trois incidents de médiation sortent « Sûr à 60 % », en orange, alors qu'une règle déterministe les a retenus.
