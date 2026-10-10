# sAIfe | fiche de défense pour le jury

Secure Horizons, Track 2 · 10–11 octobre 2026 · Orbis Pay est une entreprise fictive. [Version PDF, une page](FICHE_JURY.pdf), source LaTeX dans [FICHE_JURY.tex](FICHE_JURY.tex).

Vidéo de démo : lien à ajouter après le tournage.

## La menace défendue

Un contenu piégé vise deux lecteurs. Le salarié clique un lien trompeur, ouvre un site sosie ou valide un virement réclamé par un faux dirigeant. L’agent IA interne lit un mail qui cache une consigne, la prend pour une tâche et tente d’envoyer des données dehors avec ses propres droits. sAIfe suit les deux chemins jusqu’au même dossier SOC, où un humain décide.

Preuves hors sAIfe : 33,1 % des salariés non formés échouent aux tests de phishing simulés, 4,1 % après un an ([KnowBe4 2025](https://www.knowbe4.com/resources/reports/2025-phishing-by-industry-benchmarking-report)) ; EchoLeak, CVE-2025-32711, fuite de données par Microsoft 365 Copilot sans action humaine ([The Hacker News](https://thehackernews.com/2025/06/zero-click-ai-vulnerability-exposes.html)) ; injection de prompt via le serveur MCP de GitHub, mai 2025 ([Invariant Labs](https://invariantlabs.ai/blog/mcp-github-vulnerability)).

## Les contrôles

- Poste : l’app Mac prévient avant le geste (mail frauduleux, site louche, fichier à risque) et l’extension Chrome avant un site sosie. Le salarié choisit ; le poste n’est jamais bloqué, sauf un virement ou un export de clients, qui attend un second regard. Quatre modules qu’on peut couper (mails, onglet actif, téléchargements, agents IA du poste) ; au SOC partent la catégorie, le domaine et le choix, jamais le contenu d’un fichier ni la valeur d’un secret. La copie désarmée d’un mail frauduleux part du serveur de messagerie, pas du poste.
- Garde-mail : chaque mail est jugé sûr, suspect ou frauduleux, avec une phrase par signal (sosie, lien menteur, pièce piégée, fraude au président, consigne cachée).
- Passerelle de l’agent : désarmeur des consignes cachées avant lecture, jeton limité à la tâche, canaris, et tout envoi hors d’Orbis Pay retenu avant exécution.
- Boîte noire scellée en SHA-256 : `GET /api/incidents/{id}/verification` dit à quelle étape un dossier a été modifié ; rapport d’une page pour le RSSI.
- Exports par l’API : incident au format ECS, règles Sigma, brouillon NIS2 à relire.

Ce qu’on ne fait pas : tout bloquer, remplacer votre SIEM, classer vos documents.

## Comment l’humain garde la main

- Le salarié est prévenu avant d’agir, avec la raison, et choisit. « Annuler » envoie un événement : la SOC compte un piège évité, sans ouvrir de dossier.
- Geste critique : le relecteur IA (Haiku) accorde ou refuse en quelques secondes, à partir de faits structurés. Les règles refusent d’office un virement au-dessus de 10 000 €, un export de clients vers l’extérieur ou un geste dont le texte contient une consigne pour une IA ; en cas de panne ou de délai de plus de 8 s, ce sont les règles qui tranchent. L’analyste garde « Accorder » et « Refuser », avec motif.
- Agent : « Laisser passer » se confirme toujours ; sur un incident critique, « Couper » aussi, avec un motif obligatoire et cinq secondes pour annuler. Motif et auteur sont scellés. Sans décision, l’appel retenu est refusé.
- Le salarié apparaît sous pseudonyme ; lever son identité demande un motif, et l’acte est scellé.
- Les règles du SOC s’écrivent en français ; sAIfe montre ce qu’il a compris et n’active rien sans confirmation.
- Seuils : session classée agent IA au-dessus de 0,40 ; canari touché ou envoi externe, l’agent est suspendu ; comportement inhabituel (pic d’appels, outil jamais vu, volume lu ×10), simple alerte ; pré-tri du relecteur sous 0,7 de confiance, file « à regarder ».

Le détail, fichier par fichier, est dans la section « Comment l’humain garde la main » du README.

## Correspondances (repères, pas une certification)

| Référence | Ce que sAIfe couvre |
| --- | --- |
| OWASP Agentic ASI01, détournement d’objectif | consigne cachée d’un mail : retirée par le désarmeur, ou suivie puis arrêtée par le canari |
| ASI02, usage abusif des outils | appel d’outil retenu par la passerelle avant exécution |
| ASI03, abus d’identité et de privilèges | jeton de tâche, droits accordés comparés aux droits nécessaires, révocation |
| MITRE ATLAS | AML.T0051.001 injection indirecte par un document lu ; AML.T0053 invocation d’outil par l’agent ; AML.T0057 fuite de données |
| MITRE ATT&CK | T1566 phishing (garde-mail, extension, pop-up). T1552, T1048, T1567 et T1200 sont typés pour les gestes du poste, sans mesure |
| NIST CSF 2.0 | Détecter : DE.CM-09, DE.AE-02, DE.AE-08. Répondre : RS.MA-02, RS.AN-03, RS.MI-01 |
| NIS2, article 23 | alerte précoce sous 24 h : sAIfe prépare le brouillon, l’humain qualifie l’incident et notifie |

## Ce qu’on a mesuré

Le 10 octobre 2026 à 22 h 10, commit `a1a7321`, sur des backends isolés (port libre, base SQLite temporaire, jamais le backend partagé). Trafic et mails écrits pour la démo. Détail et dénominateurs : [mesures/resultats.md](mesures/resultats.md). Rejouer : `python3 docs/mesures/mesurer.py`.

- Agent interne piégé, joué par la vraie passerelle : 25/25 sessions classées agent IA, 25/25 incidents, 0 rapport sorti. Temps de détection : médiane 10 ms, moyenne 11 ms. Temps de confinement : médiane 19 ms, moyenne 20 ms, avec une coupure envoyée par script. 25 échantillons chacun. Incident ouvert 0,81 ms après l’événement déclencheur (médiane).
- Agent IA externe : 25/25 sessions classées agent IA, 25/25 incidents. Faux positifs : 0/50 sessions humaines ou scriptées classées agent IA.
- 12 mails de démo : 8/8 frauduleux repérés, 0/3 légitime signalé, le mail douteux classé « suspect ». Désarmeur : consigne cachée retirée dans 2/2 mails qui en portent une, 0/10 ailleurs.
- Relecteur IA sur 6 gestes critiques : 6/6 tranchés par Haiku sans repli, 1 accordé, 5 refusés, médiane 3,3 s, moyenne 3,6 s.

Non mesuré : le temps de décision d’un analyste humain, un vrai modèle dans l’agent (le cerveau est scripté), un vrai poste ou une vraie messagerie.

## Tests

555 tests réussis le 10 octobre 2026 à 22 h 12, au commit `a1a7321` : backend 195, interne 162, messagerie 73, attaque 29, poste 17, ancienne surface externe 19 (pytest), scripts de démo 34 (unittest), extension 26 (`node --test`). Les tests Swift de l’app Mac ne sont pas dans ce total. Ils vérifient le prototype, pas une détection en production.

## Limites

Trafic et mails écrits pour la démo, entreprise fictive : ces chiffres montrent la cohérence du moteur, pas une détection en production. Agent scripté, aucun vrai modèle mesuré dans l’agent. Désarmeur, analyseur de mails et extension reposent sur des motifs : une consigne paraphrasée et polie peut passer, d’où le contrôle de l’action. Le relecteur IA peut accorder à tort un geste que les règles laissent ouvert. Pas de branchement sur Outlook ou Gmail, pas d’annuaire d’identités. Prévu avant un déploiement : conservation de 90 jours, information des salariés et du CSE. SQLite et un seul écrivain. Le brouillon NIS2 n’est ni qualifié ni envoyé, et les correspondances ci-dessus n’ont été auditées par personne.

## Cible, modèle, équipe (hypothèses, aucun client)

- Cible : entreprises régulées (finance avec DORA, applicable depuis janvier 2025 ; santé), 500 à 5 000 salariés, une équipe sécurité ou SOC, au moins un agent IA en production ou en pilote avancé, Microsoft 365 ou Google Workspace, un SIEM. Hors cible : moins de 250 salariés, sans équipe sécurité ni agents.
- Personnes : le RSSI achète, l’analyste SOC utilise, le responsable IA ou data copilote, le DPO et la conformité valident, le CSE est consulté pour le volet poste.
- Modèle : licence annuelle par agent supervisé, poste salarié en option, pilote de 3 mois, pas de prix affiché. Deux hypothèses à tester en dix entretiens avec des RSSI : un RSSI finance la supervision d’agents sur un budget sécurité existant ; la licence par agent reste lisible quand le nombre d’agents monte.
- NIS2 est une directive européenne : la loi française de transposition est encore attendue, sAIfe ne la présente pas comme déjà applicable en France.
- Équipe : Guilhem (agents IA et technique), Paul (mails et business).

Parcours de démo : [DEMO_JURY.md](DEMO_JURY.md). Rejouer les mesures : `python3 docs/mesures/mesurer.py`.
