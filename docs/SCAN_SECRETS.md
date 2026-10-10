# Scan de secrets

Résultat du 10 octobre 2026, sur `44e45da` : 0 alerte, par gitleaks 8.30.1 et par `scripts/scan_secrets.py`.

## Ce qui a été scanné

| Outil | Périmètre | Résultat |
|---|---|---|
| gitleaks (`git`) | 35 commits, toutes les versions de fichiers | 0 alerte |
| gitleaks (`dir`) | arbre de travail, y compris fichiers ignorés par Git | 1 alerte, expliquée plus bas |
| `scan_secrets.py` | 169 fichiers présents, 328 objets Git (blobs, commits, tags), 23 objets ignorés (binaires ou plus de 1 Mo) | 0 alerte |

Le script Python cherche les formats de clés courants (AWS, GitHub, OpenAI, Anthropic, Google, Slack, Stripe), les clés privées, les JWT et les affectations suspectes (`password=`, `token=`…). Il n'affiche jamais une valeur trouvée, seulement la catégorie, le fichier et la ligne.

## Valeurs fictives autorisées

Les premiers passages ont signalé six valeurs, toutes inventées pour Orbis Pay. Elles sont listées une à une dans `.gitleaks.toml` et dans `VALEURS_FICTIVES` de `scripts/scan_secrets.py`, jamais par dossier : une vraie clé placée à côté reste détectée.

| Valeur | Où | Rôle |
|---|---|---|
| `ORBISPAY-CANARY-2B91-…` | `interne/donnees/documents/coffre_cles_api_archive.md` | canari de l'agent interne |
| `orbis_sk_test_votreclef` | `leurres/orbis/site.py` | exemple de la documentation du leurre |
| `sk-live-ABCDEF0123456789` | `backend/tests/test_humain.py` | secret collé dans un scénario de test |
| `sk-ant-api03-7h2Kd9fLmQ0zXc4Vb1Np` | `poste/garde/simulateur.py`, `poste/tests/test_garde.py` | clé de démonstration du simulateur |
| `sk-ant-api03-secret-tres-long-xyz` | `poste/tests/test_garde.py` | fixture de masquage |
| `AKIA1234567890ABCDEF` | `poste/tests/test_garde.py` | fixture de détection AWS |

L'alerte restante de `gitleaks dir` porte sur `design.pen` (champ `fileToken`, un UUID). Ce fichier est local, ignoré par `.gitignore` et absent de l'historique.

Aucune clé réelle n'a été trouvée, donc rien n'a été retiré de l'historique.

## Relancer

```bash
git config core.hooksPath .githooks              # active le hook pre-commit
python3 scripts/scan_secrets.py --self-test      # vérifie le détecteur
python3 scripts/scan_secrets.py                  # arbre et historique (code de sortie 0, 1 ou 2)
python3 scripts/scan_secrets.py --staged         # ce qui va être commité
gitleaks git . --config .gitleaks.toml --redact  # historique
gitleaks dir . --config .gitleaks.toml --redact  # arbre
```

Gitleaks s'installe avec `brew install gitleaks`. Le hook `.githooks/pre-commit` lance gitleaks s'il est présent, puis le script Python, et refuse le commit au premier secret probable. Avec un jeton synthétique indexé dans un index temporaire, le hook a bien bloqué le commit.

## Limites

Un scanner à motifs ne prouve pas l'absence de secret : il ne voit que les formats prévus et les entropies élevées. Le script ne lit ni les fichiers ignorés par Git (`.env`, bases locales) ni les binaires, et ne voit que les références Git présentes sur la machine. `.env` est ignoré et seul `.env.example`, sans valeur, est suivi.
