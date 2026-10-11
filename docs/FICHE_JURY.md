# sAIfe | fiche de défense pour le jury

Secure Horizons, Track 2 · 10–11 octobre 2026 · Orbis Pay est une entreprise fictive. [Version PDF, une page](FICHE_JURY.pdf), source LaTeX dans [FICHE_JURY.tex](FICHE_JURY.tex).

Vidéo de démo : [video/sAIfe-demo.mp4](video/sAIfe-demo.mp4).

## La menace défendue

Un contenu piégé vise deux lecteurs. Le salarié clique un lien trompeur, ouvre un site sosie ou valide un virement réclamé par un faux dirigeant. L’agent IA interne lit un mail qui cache une consigne, la prend pour une tâche et tente d’envoyer des données dehors avec ses propres droits. sAIfe suit les deux chemins jusqu’au même dossier SOC, où un humain décide.

Preuves hors sAIfe : 33,1 % des salariés non formés échouent aux tests de phishing simulés, 4,1 % après un an ([KnowBe4 2025](https://www.knowbe4.com/resources/reports/2025-phishing-by-industry-benchmarking-report)) ; EchoLeak, CVE-2025-32711, fuite de données par Microsoft 365 Copilot sans action humaine ([The Hacker News](https://thehackernews.com/2025/06/zero-click-ai-vulnerability-exposes.html)) ; injection de prompt via le serveur MCP de GitHub, mai 2025 ([Invariant Labs](https://invariantlabs.ai/blog/mcp-github-vulnerability)).

## Les contrôles

- Poste : l’app Mac prévient avant le geste (mail frauduleux, site louche, fichier à risque) et tient l’inventaire des agents IA du poste ; l’extension Chrome arrête un site sosie ou louche, avec les mêmes règles. Le salarié choisit ; le poste n’est jamais bloqué ni verrouillé. Quatre modules qu’on peut couper (mails, onglet actif, téléchargements, agents IA du poste) ; au SOC partent la catégorie, le domaine et le choix. Pour un mail jugé frauduleux, une copie désarmée part du serveur de messagerie ; sinon, jamais le contenu d’un fichier ni la valeur d’un secret.
- Geste critique (virement, export de clients) : l’app du poste le déclare à sAIfe (appel local `/avertir`, ou geste repéré dans un mail), et des règles y cherchent un signal de risque avant de laisser le salarié continuer ; rien ne s’interpose dans le vrai flux de paiement, ce branchement est une étape de déploiement. Sans signal, le geste part sans pop-up. Signal sans fraude (RIB qui change, bénéficiaire inconnu, montant hors des habitudes) : retenu, le responsable ou la finance le tranche dans l’espace `/validation`. Signal de fraude (geste après un mail frauduleux, consigne cachée, rafale) : relecteur IA et incident SOC.
- Garde-mail : chaque mail est jugé sûr, suspect ou frauduleux, avec une phrase par signal (sosie, lien menteur, pièce piégée, fraude au président, consigne cachée).
- Passerelle de l’agent : désarmeur des consignes cachées avant lecture, jeton limité à la tâche, canaris, envoi hors d’Orbis Pay retenu avant exécution. Médiation de tous les outils : un outil absent de l’inventaire de l’agent, un outil de lecture détourné pour sortir une donnée (paramètres décodés en URL, base64, hexadécimal) et un outil MCP modifié en cours de session sont retenus avant exécution. Coût : 0,07 ms de plus en médiane sur un appel autorisé.
- Journal chaîné en SHA-256, signé en Ed25519 par le backend (une clé locale par canal d’origine), en ajout seul : `GET /api/incidents/{id}/verification` nomme le champ modifié. Qui n’a que la base ne peut pas la réécrire sans que ça se voie ; qui tient la machine, oui. Rapport d’une page pour le RSSI. Ancrage sur Avalanche : voie d’exploration, aucune ancre publiée.
- Intégrations : export ECS 8.11, CEF par syslog, 29 règles Sigma validées par sigma-cli, webhooks Slack et Teams, SMS simulé, résumé du lundi, brouillon NIS2 à relire ([INTEGRATIONS.md](INTEGRATIONS.md)). Quatre identités authentifiées : analyste, passerelle, poste, validateur.

Ce qu’on ne fait pas : tout bloquer, remplacer votre SIEM, classer vos documents.

## Comment l’humain garde la main

- Le salarié est prévenu avant d’agir, avec la raison, et choisit. « Annuler » envoie un événement : la SOC compte un piège évité, sans ouvrir de dossier.
- Relecteur IA (Claude Haiku, d’Anthropic) : il reçoit des faits établis par sAIfe, jamais le mail. Les règles dures passent avant lui (plafond de 10 000 € pour un bénéficiaire hors liste, RIB qui change, consigne cachée, rafale) ; en cas de panne ou de délai de plus de 8 s, les règles tranchent et retiennent dans le doute. Sur un signal de fraude, rien n’est accordé en silence. Sa mémoire ne reçoit que des décisions humaines signées. L’analyste garde « Accorder » et « Refuser », avec un motif scellé.
- Le responsable ou la finance voit le montant, le bénéficiaire et la raison d’un geste retenu, et décide avec un motif signé. La sécurité n’apprend que l’issue.
- Besoin d’en connaître : le SOC lit des tranches de montant, bénéficiaires et IBAN masqués, salariés sous pseudonyme. Le détail s’ouvre sur un signal de fraude, et chaque consultation entre au journal scellé. Lever l’identité d’un salarié demande un motif, scellé lui aussi.
- Agent : « Laisser passer » se confirme toujours ; sur un incident critique, « Couper » aussi, avec un motif obligatoire et cinq secondes pour annuler. Sans décision, l’appel retenu est refusé.
- Règles en français : chaque phrase lance un agent jetable (six outils qui n’écrivent pas, 20 s, jeton révoqué à la fin). sAIfe montre ce qu’il a compris et ce qu’il n’a pas su traduire, et n’active rien sans clic. Le retrait des droits en trop est réel : la passerelle refuse ensuite les appels qui en ont besoin.
- Seuils : session classée agent IA au-dessus de 0,40 ; canari, envoi externe ou outil inconnu, l’agent est suspendu ; droit retiré, tentative bloquée et incident ; comportement inhabituel (pic d’appels, outil jamais vu, volume lu ×10), simple alerte ; pré-tri du relecteur sous 0,7 de confiance, file « à regarder ».

Le détail, fichier par fichier, est dans la section « Comment l’humain garde la main » du README.

## Correspondances (repères, pas une certification)

| Référence | Ce que sAIfe couvre |
| --- | --- |
| OWASP Agentic ASI01, détournement d’objectif | consigne cachée d’un mail : retirée par le désarmeur, ou suivie puis arrêtée par le canari |
| ASI02, usage abusif des outils | chaque appel d’outil contrôlé avant exécution, outils inconnus, détournés ou modifiés compris |
| ASI03, abus d’identité et de privilèges | jeton de tâche, droits accordés comparés aux droits nécessaires, retrait des droits en trop |
| MITRE ATLAS | AML.T0051.001 injection indirecte par un document lu ; AML.T0053 invocation d’outil par l’agent ; AML.T0057 fuite de données |
| MITRE ATT&CK | T1566 phishing (garde-mail, extension, pop-up) ; T1657 virement frauduleux, T1048 et T1555 dans les règles Sigma |
| NIST CSF 2.0 | Détecter : DE.CM-09, DE.AE-02, DE.AE-08. Répondre : RS.MA-02, RS.AN-03, RS.MI-01 |
| NIS2, article 23 | alerte précoce sous 24 h : sAIfe prépare le brouillon, l’humain qualifie l’incident et notifie |

## Ce qu’on a mesuré

Le 11 octobre 2026 à 9 h 35, commit `fb6fa41`, sur des backends isolés (port libre, base SQLite temporaire, jamais le backend partagé). Trafic et mails écrits pour la démo ; les durées sont celles de la chaîne technique sur le banc, pas une cadence d’attaque ni une prédiction de production. Détail et dénominateurs : [mesures/resultats.md](mesures/resultats.md). Rejouer : `python3 docs/mesures/mesurer.py`.

- Agent interne piégé, joué par la vraie passerelle : 25/25 sessions classées agent IA, 25/25 incidents, 0 rapport sorti. Temps de détection : médiane 12 ms, moyenne 17 ms. Temps de confinement : médiane 32 ms, moyenne 31 ms, avec une coupure envoyée par script. 25 échantillons chacun. Incident ouvert 1,52 ms après l’événement déclencheur (médiane).
- Agent IA externe : 25/25 sessions classées agent IA, 25/25 incidents. Faux positifs : 0/50 sessions humaines ou scriptées classées agent IA.
- 12 mails de démo : 8/8 frauduleux repérés, 0/3 légitime signalé, le mail douteux classé « suspect ». Désarmeur : consigne cachée retirée dans 2/2 mails qui en portent une, 0/10 ailleurs.
- Relecteur IA sur 6 gestes critiques : 4 refusés d’office par les règles dures (modèle non appelé), 2 relus par Haiku (1 accordé, 1 retenu) en 4,0 s et 4,8 s.
- Mode réel, 11 octobre : Haiku pilote l’agent sur de vrais services locaux (Mailpit, API bancaire locale, fichiers) et a résisté à l’injection, 0 tentative sur 3 puis 0 sur 5. Un attaquant déterministe sur les mêmes services : le mail d’exfiltration est livré sans sAIfe, retenu avec ([REEL_OU_SIMULE.md](REEL_OU_SIMULE.md)).

Non mesuré : le temps de décision d’un analyste ou d’un responsable humain, un vrai poste ou une vraie messagerie.

## Tests

926 tests réussis le 11 octobre 2026 à 8 h 55, au commit `cb8b6bc` : backend 522, interne 205, messagerie 73, attaque 29, poste 17, ancienne surface externe 19 (pytest), scripts de démo 35 (unittest), extension 26 (`node --test`). Les tests Swift de l’app Mac ne sont pas dans ce total. Ils vérifient le prototype, pas une détection en production.

## Limites

Trafic et mails écrits pour la démo, entreprise fictive : ces chiffres montrent la cohérence du moteur, pas une détection en production. Désarmeur, analyseur de mails et extension reposent sur des motifs : une consigne paraphrasée et polie peut passer, d’où le contrôle de l’action. Le relecteur IA reste attaquable comme tout modèle ; les règles dures passent avant lui. Pas de branchement sur Outlook ou Gmail, et le volet poste n’existe que sur macOS et dans Chrome. Un jeton par rôle, pas par personne ; SQLite et un seul écrivain. Prévu avant un déploiement : purge à 90 jours, analyse d’impact, information des salariés et du CSE, relecteur sur un modèle hébergé dans l’UE ou en mode règles. Le brouillon NIS2 n’est ni qualifié ni envoyé, et les correspondances ci-dessus n’ont été auditées par personne.

## Feuille de route

Demandé par les testeurs (des personas joués par des agents, pas de vraies personnes), pas fait pour le 11 octobre : une app Windows, Microsoft 365 (Outlook et Exchange, puis Google Workspace), le SSO (OIDC) avec les rôles et le rattachement aux responsables tirés de l’annuaire. Ensuite : l’ancrage du journal sur Avalanche, l’envoi réel des SMS et du résumé du lundi, les connecteurs Sentinel et Splunk.

## Cible, modèle, équipe (hypothèses, aucun client)

- Cible : entreprises régulées (finance avec DORA, applicable depuis janvier 2025 ; santé), 500 à 5 000 salariés, une équipe sécurité ou SOC, au moins un agent IA en production ou en pilote avancé, Microsoft 365 ou Google Workspace, un SIEM. Pas la première cible : moins de 250 salariés, sans équipe sécurité ni agents ; une PME sans SOC peut s’en servir avec la validation par le responsable et le résumé du lundi.
- Personnes : le RSSI achète, l’analyste SOC utilise, le responsable métier ou la finance confirme les gestes retenus, le responsable IA ou data copilote, le DPO et la conformité valident, le CSE est consulté pour le volet poste.
- Modèle : licence annuelle par agent supervisé, poste salarié en option, pilote de 3 mois, pas de prix affiché. Deux hypothèses à tester en dix entretiens avec des RSSI : un RSSI finance la supervision d’agents sur un budget sécurité existant ; la licence par agent reste lisible quand le nombre d’agents monte.
- NIS2 est une directive européenne : la loi française de transposition est encore attendue, sAIfe ne la présente pas comme déjà applicable en France.
- Équipe : Guilhem (agents IA et technique), Paul (mails et business).

Parcours de démo : [DEMO_JURY.md](DEMO_JURY.md). Rejouer les mesures : `python3 docs/mesures/mesurer.py`.
