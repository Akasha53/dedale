# interne/ — agent interne d'Orbis Pay et passerelle boîte noire

Port 8702 (réservé pour un futur service HTTP ; le cœur fonctionne en bibliothèque).

## Ce que fait le module

Un petit assistant d'entreprise réaliste répond à une demande d'employé (« résume mes
mails de la semaine »). Il a une boîte mail et des documents **synthétiques** (`donnees/`)
et quatre outils : `lire_mail`, `chercher_document`, `resumer`, `envoyer_rapport`.

**Tout passe par la passerelle** (`orbis/passerelle.py`), la « boîte noire » :

1. elle journalise au backend (`entree_agent`, `appel_outil` avec ses paramètres,
   `sortie_agent`) via `POST /api/evenements` ;
2. elle inspecte les sorties et les appels sortants (`envoyer_rapport`, réponse finale) :
   - **exfiltration EchoLeak** : lien ou image markdown vers un domaine externe ;
   - **usage d'un faux secret canari** : un jeton canari apparaît en sortie ;
3. dès qu'un canari est touché, elle **retient l'appel en cours**, journalise
   `leurre_touche`, et interroge `GET /api/sessions/{id}` chaque seconde jusqu'à la
   décision de l'analyste : `active` → reprise, `coupee` → arrêt de l'agent + jeton révoqué.
   Jamais de coupure automatique sans décision du backend ; si le backend reste muet,
   l'appel est refusé (containment faible) mais le jeton n'est pas révoqué.

Les canaris (`orbis/canaris.py`) portent un identifiant unique `C-xxxx` par mail ou
document, enregistré au démarrage via `POST /api/leurres`. Un humain ne les déclenche pas.

## Cerveau de l'agent

Interface unique `prochaine_action(demande, historique)`. Trois implémentations
(`orbis/cerveau.py`) :

- `CerveauApi` — SDK Anthropic, si `ANTHROPIC_API_KEY` est présent ;
- `CerveauCli` — repli par `claude -p` en sous-processus (voie testée et fonctionnelle ici) ;
- `CerveauScripte` — déterministe, pour les tests et la démo reproductible ; tempéraments
  `prudent` (ignore la consigne cachée) et `naif` (la suit → se fait piéger).

`DEDALE_CERVEAU` (`auto` par défaut : API si clé, sinon CLI) force le choix.

## Lancer

```bash
cd interne
uv venv --python 3.12 && uv pip install pytest
uv run python -m orbis.demo          # démo autonome : backend simulé + cerveau scripté
uv run python -m orbis.demo --cerveau cli        # pilote un vrai agent via claude -p
uv run python -m orbis.demo --backend-reel       # tape le vrai backend sur 8700
uv run pytest -q                      # 14 tests
```

La démo joue trois scènes : session normale (aucun canari), session détournée où
l'analyste **coupe** (jeton révoqué, rien n'est exfiltré), session détournée où l'analyste
**valide** (reprise).

Tout est fictif et local : aucun système réel, aucune donnée réelle, aucun secret réel.
