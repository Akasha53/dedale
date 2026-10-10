# poste/ : le garde du corps du poste du salarié

Avenant « humain, le maillon faible » de Dédale. Un agent local observe une
action risquée **avant** qu'elle n'aboutisse, décide selon des règles claires,
avertit le salarié et le laisse choisir (continuer / annuler). Non bloquant :
il prévient. Chaque avertissement et chaque choix part au backend
(`source: humain`, `surface: poste`). Si le salarié passe outre, l'événement
d'incident part aussi. Rien d'autre ne quitte le poste. Si le backend ne répond
pas, le poste continue (il ne tombe jamais).

Tout est fictif et local : entreprise Orbis Pay, salariée « Camille ».

## Les deux gestes vedettes

Le produit se montre sur deux moments, dans cet ordre :

1. **Un mail reçu frauduleux.** Camille ouvre un mail qui se réclame d'Orbis Pay.
   Au moment de la lecture, le garde du corps lit l'expéditeur et le lien du
   corps, avant tout clic, et prévient : « Ce mail est sûrement frauduleux. »
2. **Un lien piégé en naviguant.** Camille clique un résultat sponsorisé qui
   imite la page de connexion. Le garde du corps le voit avant la saisie des
   identifiants : « Ce lien n'est pas le vrai site d'Orbis Pay. »

Les deux portent la catégorie `phishing`. Le reste (secret collé, mail sensible
vers l'extérieur, dépôt sur une IA non validée, pièce jointe piégée) reste
surveillé, au second plan.

## Règles de détection

| Incident | Règle | Déclenche quand |
|---|---|---|
| `humain_phishing` (mail reçu) | mail frauduleux à l'ouverture | lien du corps piégé, expéditeur en liste noire ou sosie d'`orbispay`, nom affiché usurpé, ou appât aux identifiants depuis un expéditeur externe |
| `humain_phishing` (navigation web) | lien piégé cliqué sur le web | liste noire, IP nue, ruse `@`, punycode, sosie « orbispay », TLD inhabituel |
| `humain_phishing` (pièce jointe) | pièce jointe piégée | exécutable, double extension (`facture.pdf.exe`), macro externe |
| `humain_secret` | secret dans ce qui est collé/saisi | clé privée, clé AWS/Anthropic/OpenAI/Google/GitHub/Slack, ou `mot de passe=…`, repéré dans un texte collé vers une surface **hors** `orbispay.example` |
| `humain_mail_externe` | mail sortant + données sensibles | au moins un destinataire hors domaine **et** pièce/corps sensible (clients, IBAN, export, paie, contrat…) |
| `humain_upload_ia` | dépôt confidentiel hors outils validés | fichier confidentiel déposé sur un service **absent** de la liste DSI (IA non autorisée, cloud perso) |

Chaque avertissement part à la console avec sa `categorie` courte
(`phishing`, `secret`, `mail_externe`, `upload_ia`), son `choix` (`continuer` /
`annuler`) et son `contexte` (mail reçu, navigation web, pièce jointe…).

La preuve (secret, lien, expéditeur) est renvoyée **neutralisée** : tronquée
et préfixée `[preuve, neutralisée]`, jamais réexécutée. Un secret ne laisse fuir
ni sa valeur ni son préfixe, seulement sa catégorie et sa longueur.

## La pop-up

- **Terminal** : `garde.popup.rendu_terminal(verdict)`, encadré net, filmable.
- **HTML autonome** : `demo/popup.html`. Deux scènes jouées côte à côte, un
  client mail avec le mail frauduleux ouvert et un navigateur sur la fausse page
  de connexion, la fenêtre du garde du corps par-dessus et les deux issues
  (annulé = protégé, passé outre = incident). Régénérée par le simulateur.

## Lancer

```bash
cd poste
uv run --extra dev pytest -q                 # tests (17)
uv run python -m garde.simulateur            # journée simulée → backend 8700 si présent
uv run python -m garde.simulateur --sans-reseau   # démo hors ligne (ne poste rien)
uv run python -m garde.simulateur --choix continuer|annuler|mix
```

Le simulateur ouvre la journée sur les deux gestes vedettes, puis joue le reste
(10 gestes, 4 sûrs, 6 risqués), montre les pop-up terminal, poste les événements
et écrit `demo/popup.html`.

## Code

- `garde/actions.py` — le geste observé (`Geste`, natures : mail reçu/clic/coller/mail/dépôt/pièce).
- `garde/detection.py` — les règles (`evaluer` → `Verdict`), neutralisation des preuves.
- `garde/garde_du_corps.py` — orchestration : détecter → avertir → choix → événements, escalade SOC.
- `garde/backend.py` — client `POST /api/evenements` (urllib, fire-and-forget).
- `garde/popup.py` — rendu terminal et page HTML.
- `garde/simulateur.py` — la journée de Camille.
