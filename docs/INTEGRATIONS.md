# Intégrations de sAIfe

sAIfe parle aux outils que les entreprises ont déjà : le SIEM du SOC (Elastic, Splunk, ArcSight, Wazuh), Teams ou Slack, le téléphone d'astreinte, et la boîte mail de la direction. Ce document dit ce qui existe, comment le brancher, et ce qui manque pour la production. Le contrat exact des champs et des routes est dans `CONTRATS.md`, avenant « intégrations SIEM, alertes par rôle, résumé du lundi ».

Trois testeurs ont fixé le cahier des charges :

| Testeur | Demande | Réponse |
|---|---|---|
| RSSI d'une ETI, SOC externalisé | les alertes dans le SIEM du prestataire | transfert syslog CEF, export ECS 8.x, webhook vers le canal du SOC |
| DSI d'un cabinet sans SOC | un mail le lundi, un SMS pour un geste critique | résumé du lundi, SMS d'astreinte (simulé) |
| Responsable sécurité IA d'une mutuelle | un export Sigma réutilisable | une règle Sigma par type d'incident, sur des champs ECS, validée par sigma-cli |

Pendant la démo, rien ne sort de la machine. Le SMS n'est jamais envoyé : il est écrit dans un journal local et la console en montre le texte. Un webhook ou un transfert syslog ne part que si sa variable est posée, et le faux SIEM de démo n'écoute que sur 127.0.0.1.

## Ce qui existe

### Export ECS 8.x

`GET /api/incidents/{id}/export?format=ecs` rend un document ECS 8.11 par événement. Les valeurs de `event.kind`, `event.category` et `event.type` sont celles qu'ECS autorise, et un test le vérifie. L'événement qui porte le signal est un `alert` avec sa technique ATT&CK dans `threat.technique.*`. Un salarié n'y figure que sous pseudonyme (`user.name: "Salarié 7751"`).

### Règles Sigma

`sigma/types/` contient 29 règles : une par type d'incident, quatre règles de geste (virement et export à double validation, coffre de clés lu par un agent, virement tenté par un agent) et quatre variantes qui tournent sur les journaux du client sans sAIfe. Ce sont le domaine sosie et le dépôt vers une IA publique vus par le proxy, l'envoi vers un service de collecte, et les routes-leurres vues par le serveur web. Chaque règle a un `id` stable, des étiquettes ATT&CK (T1078, T1555, T1657, T1195, T1048, T1566…) et des faux positifs. L'export d'un incident (`?format=sigma`) rend les règles qui l'attrapent et la variante spécialisée sur le domaine ou la route qu'il a vus.

### CEF et syslog

`?format=cef` rend une ligne CEF par événement. Avec `DEDALE_SYSLOG=udp://hôte:port` (ou `tcp://`), chaque changement d'un incident part au SIEM en une ligne CEF dans une trame RFC 5424.

### Alertes par rôle

Un geste retenu sans signal de fraude prévient le validateur métier (le responsable du salarié ou la finance) : le geste, une tranche de montant, le service, le lien vers l'espace de validation. Une menace prévient le SOC par webhook dès la gravité moyenne, et par SMS quand elle est critique. Un message au SOC ne contient jamais de montant ni de bénéficiaire. Le webhook sort au format Slack, Teams (carte adaptative) ou JSON.

### Résumé du lundi

`GET /api/resume-hebdo` rend le mail de la semaine : les menaces, les gestes retenus et leur issue, les agents à surveiller, les règles qui ont joué. Une phrase par point, sans jargon ni nom. La console l'affiche dans Mesures, bouton « Voir le mail ».

## Le brancher

Démo complète sur une machine :

```bash
# 1. Faux SIEM et faux Teams (127.0.0.1) : affiche chaque trame et chaque webhook
cd backend && uv run python -m app.recepteur_siem --syslog-port 8791 --webhook-port 8792

# 2. Backend, dans un autre terminal
export DEDALE_SYSLOG=udp://127.0.0.1:8791
export DEDALE_NOTIF_SOC_URL=http://127.0.0.1:8792/soc DEDALE_NOTIF_SOC_FORMAT=teams
export DEDALE_NOTIF_VALIDATION_URL=http://127.0.0.1:8792/validation DEDALE_NOTIF_VALIDATION_FORMAT=json
cd backend && uv run uvicorn app.main:app --port 8700

# 3. Les SMS qui seraient partis
tail -f data/sms-demo.log
```

Dans la console, sur un dossier : « Exporter », puis « Alertes et SMS » montre qui est prévenu, le texte exact du SMS avec son nombre de segments, et la ligne CEF transmise.

Chez un client :

| Cible | Branchement |
|---|---|
| Elastic | indexer `documents[]` de l'export ECS ; les champs sont déjà ECS, aucun pipeline de renommage |
| Splunk, Elastic, ES\|QL | `sigma convert -t splunk --without-pipeline sigma/types/` (ou `-t lucene`, `-t esql`) |
| ArcSight, QRadar, Wazuh, rsyslog | `DEDALE_SYSLOG=tcp://collecteur:514`, lignes CEF en RFC 5424, facilité local4 |
| Teams | URL d'un flux Workflows « quand une requête webhook est reçue » dans `DEDALE_NOTIF_SOC_URL`, format `teams` |
| Slack | URL d'un webhook entrant, format `slack` |
| Autre outil | format `json` : `{source, version, regle, destinataire, gravite, reference, titre, texte, lien, faits}` |

Pour valider les règles : `uv tool install sigma-cli --with pysigma-backend-splunk --with pysigma-backend-elasticsearch`, puis `sigma check sigma/`. Résultat au 11 octobre : 0 erreur, 0 avertissement. Le test `test_sigma_cli_valide_et_convertit` le refait, avec une conversion Splunk et Lucene, quand `sigma` est installé. La capture `captures/integrations/sigma-convertie.png` montre la règle du domaine sosie traduite pour Splunk, Lucene et ES|QL.

## Ce qui reste à faire en production

### SMS réel

Remplacer l'écriture dans le journal par un fournisseur d'envoi (API d'un opérateur ou d'un agrégateur), avec les numéros d'astreinte tirés de l'annuaire, un accusé de réception et un nouvel essai. Le texte garde ses règles : deux segments au plus, ni montant ni bénéficiaire pour le SOC.

### Connecteur Microsoft Sentinel

Deux voies. La première passe par l'agent Azure Monitor sur un relais syslog : les lignes CEF arrivent dans la table `CommonSecurityLog` sans code de plus. La seconde est un connecteur par l'API d'ingestion de Logs (règle de collecte et table personnalisée) qui pousse les documents ECS. Les règles Sigma se convertissent pour Sentinel avec le backend KQL de pySigma, non installé ici.

### Splunk HEC

Envoyer les documents ECS au HTTP Event Collector (`/services/collector/event`, jeton HEC, `sourcetype` dédié) plutôt que par syslog : on garde la structure JSON et l'accusé de réception.

### Le reste

- Syslog en TLS (RFC 5425) : aujourd'hui UDP ou TCP en clair. En attendant, passer par un rsyslog local qui relaie en TLS.
- File d'envoi persistante : l'historique et le dédoublonnage vivent en mémoire, un webhook en échec n'est pas relancé, et un redémarrage peut renvoyer une alerte sur un dossier encore ouvert.
- Envoi réel du résumé du lundi (SMTP signé DKIM, destinataires par entreprise) ; aujourd'hui, aperçu seulement.
- Secrets : les URL de webhook et le jeton HEC dans un coffre, pas en variables d'environnement.
- Règles Sigma : remplacer la marque fictive Orbis Pay par celle du client dans la variante « domaine sosie », et la liste des services d'IA autorisés dans la variante « dépôt vers une IA publique ».
