# Règles Sigma — traces Dédale (agents IA + pilier humain)

Règles génériques sur les traces, complémentaires du tri en direct du backend.
Le backend reste la détection temps réel ; ces règles servent à rejouer les traces dans un SIEM
du SOC (Elastic, Wazuh) et à partager la détection dans un format standard.

Agents IA :

| Fichier | Ce qu'elle attrape | Niveau |
|---|---|---|
| `consigne_cachee_suivie.yml` | consigne cachée d'un leurre déclenchée | high |
| `appel_outil_apres_lecture.yml` | action sur une route découverte dans un document | high |
| `exfiltration_sortie_agent.yml` | tentative de sortie de données | critical |
| `reponse_contre_injection.yml` | agent qui avoue son objectif après contre-injection | high |
| `cadence_agent_palisade.yml` | cadence régulière ~1,7 s (repère Palisade) | medium |

Pilier humain (le maillon faible) :

| Fichier | Ce qu'elle attrape | Niveau |
|---|---|---|
| `salarie_passe_outre_avertissement.yml` | salarié qui clique « continuer » malgré l'avertissement du poste | high |
| `fichier_confidentiel_vers_ia.yml` | dépôt d'un fichier confidentiel vers une IA non autorisée (shadow AI) | high |

Champs humains : `event.action = avertissement`, `dedale.details.categorie`
(`secret`/`mail_externe`/`upload_ia`/`phishing`/`intrusion_physique`),
`dedale.details.choix` (`continuer`/`annuler`), `dedale.details.gravite`, `dedale.details.cible`.

## Champs attendus

Les règles ciblent les champs produits par l'export ECS du backend
(`GET /api/incidents/{id}/export?format=ecs`), avec `logsource.product = dedale` :

- `event.action` : type d'événement Dédale (`requete`, `appel_outil`, `leurre_touche`,
  `sortie_agent`, `entree_agent`, `riposte`) ;
- `dedale.session_id`, `dedale.surface`, `dedale.leurre_id`, `dedale.leurre_nature`,
  `dedale.outil` ;
- `dedale.details.*` : `exfiltration`, `decouvert_dans_doc`, `objectif`,
  `repond_contre_injection`, `cadence_s` ;
- `user_agent.original`, `url.path`, `source.ip` (champs ECS standards).

## Vérifier la syntaxe

```bash
uvx --from sigma-cli sigma check sigma/      # ou : pip install sigma-cli ; sigma check sigma/
```

## Brancher sur Elastic

1. Ingérer l'export ECS du backend dans un index (les documents sont déjà au format ECS) :
   ```bash
   curl -s "http://127.0.0.1:8700/api/incidents/INC-0001/export?format=ecs" \
     | jq -c '.documents[]' | while read d; do
         curl -s -XPOST "http://localhost:9200/dedale-events/_doc" -H 'content-type: application/json' -d "$d"; done
   ```
2. Convertir les règles vers une requête Elastic :
   ```bash
   sigma convert -t lucene -p ecs_windows sigma/   # adapter le pipeline au mapping dedale.*
   ```
   Pour un mapping propre, écrire un petit pipeline Sigma qui laisse `dedale.*` tel quel
   (les champs sont déjà ECS-compatibles).

## Brancher sur Wazuh

1. Convertir vers le backend de Wazuh ou traduire la logique en règles XML Wazuh
   (`<rule>` + `<field>` sur les champs JSON décodés).
2. Décoder les documents ECS avec un décodeur JSON Wazuh, puis écrire les règles sur
   `event.action`, `dedale.leurre_nature`, `dedale.details.exfiltration`, etc.
3. Niveaux Sigma → niveaux Wazuh : medium≈8, high≈12, critical≈14.

Toutes les valeurs de `dedale.details.*` issues d'une surface piégée sont déjà neutralisées par
le backend : le SIEM reçoit de la donnée inerte, jamais une instruction réinjectable.

## Catalogue par type d'incident (`types/`)

`sigma/types/` contient une règle par type d'incident, quatre règles de geste et quatre variantes
qui tournent sur les journaux du proxy ou du serveur web du client, toutes sur des champs ECS 8.x.
Ces fichiers sont générés : ne pas les modifier à la main.

```bash
cd backend && uv run python -m app.sigma_regles --ecrire ../sigma/types
sigma check sigma/                                            # 0 erreur, 0 avertissement
sigma convert -t splunk --without-pipeline sigma/types/       # ou -t lucene, -t esql
```

Détail des champs et de l'export par incident : `docs/INTEGRATIONS.md` et l'avenant
« intégrations SIEM » de `CONTRATS.md`.
