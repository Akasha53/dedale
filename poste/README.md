# poste/ : le garde du corps du poste du salarié

Avenant « humain, le maillon faible » de Dédale. Un agent local observe une
action risquée **avant** qu'elle n'aboutisse, décide selon des règles claires,
avertit le salarié et le laisse choisir (continuer / annuler). Non bloquant :
il prévient. Chaque avertissement et chaque choix part au backend
(`source: humain`, `surface: poste`). Si le salarié passe outre, l'événement
d'incident part aussi. Rien d'autre ne quitte le poste. Si le backend ne répond
pas, le poste continue (il ne tombe jamais).

Tout est fictif et local : entreprise Orbis Pay, salariée « Camille ».

## Règles de détection

| Incident | Règle | Déclenche quand |
|---|---|---|
| `humain_secret` | secret dans ce qui est collé/saisi | clé privée, clé AWS/Anthropic/OpenAI/Google/GitHub/Slack, ou `mot de passe=…`, repéré dans un texte collé vers une surface **hors** `orbispay.example` |
| `humain_mail_externe` | mail externe + données sensibles | au moins un destinataire hors domaine **et** pièce/corps sensible (clients, IBAN, export, paie, contrat…) |
| `humain_upload_ia` | dépôt confidentiel hors outils validés | fichier confidentiel déposé sur un service **absent** de la liste DSI (IA non autorisée, cloud perso) |
| `humain_phishing` | lien ou pièce jointe piégés | lien : liste noire, IP nue, ruse `@`, punycode, sosie « orbispay », TLD inhabituel ; pièce : exécutable, double extension (`facture.pdf.exe`), macro externe |

La preuve (secret, lien, destinataire) est renvoyée **neutralisée** : tronquée
et préfixée `[preuve, neutralisée]`, jamais réexécutée. Un secret ne laisse fuir
ni sa valeur ni son préfixe, seulement sa catégorie et sa longueur.

## La pop-up

- **Terminal** : `garde.popup.rendu_terminal(verdict)` — encadré net, filmable.
- **HTML autonome** : `demo/popup.html`, la fenêtre d'avertissement par-dessus une
  maquette du poste (ouvrir dans un navigateur). Régénérée par le simulateur.

## Lancer

```bash
cd poste
uv run --extra dev pytest -q                 # tests (14)
uv run python -m garde.simulateur            # journée simulée → backend 8700 si présent
uv run python -m garde.simulateur --sans-reseau   # démo hors ligne (ne poste rien)
uv run python -m garde.simulateur --choix continuer|annuler|mix
```

Le simulateur joue 10 gestes (5 sûrs, 5 risqués), montre les pop-up terminal,
poste les événements et écrit `demo/popup.html`.

## Code

- `garde/actions.py` — le geste observé (`Geste`, natures : coller/mail/dépôt/clic/pièce).
- `garde/detection.py` — les règles (`evaluer` → `Verdict`), neutralisation des preuves.
- `garde/garde_du_corps.py` — orchestration : détecter → avertir → choix → événements, escalade SOC.
- `garde/backend.py` — client `POST /api/evenements` (urllib, fire-and-forget).
- `garde/popup.py` — rendu terminal et page HTML.
- `garde/simulateur.py` — la journée de Camille.
