# Dédale | fiche de défense pour le jury

Secure Horizons, Track 2 · 10–11 octobre 2026 · Orbis Pay est une entreprise fictive.

[Version PDF, une page](FICHE_JURY.pdf).

## Le point à défendre

Dédale suit deux chemins vers le même risque : un salarié sur le point de faire un geste dangereux et un agent IA qui prend une instruction hostile pour une consigne de travail. Dans les deux cas, le SOC voit les faits, la décision humaine et le résultat. La preuve technique du Track 2 est l’appel d’outil de l’agent retenu par une passerelle après lecture d’un mail piégé.

## Démonstration, dans cet ordre

1. **Salarié.** Camille ouvre un faux mail. Le garde du poste *simulé* avertit avant le clic. « Annuler » évite le geste ; « continuer » ouvre un incident. Le SOC ne coupe pas son poste.
2. **Agent.** Un agent interne *scripté* lit une instruction cachée dans un mail et tente un appel d’outil. La passerelle retient cet appel. Le SOC voit la source, l’instruction, l’outil et les droits, puis choisit : **couper** révoque le jeton ; **reprendre** libère l’appel retenu. Le rapport de la démo reste fictif et local.
3. **Preuve commune.** La console montre la chaîne, l’état final, l’auteur de la décision et les exports ECS/Sigma. Le document NIS2 est un brouillon à qualifier ; rien n’est notifié automatiquement.

## Questions probables

| Objection | Réponse à donner |
| --- | --- |
| « C’est une campagne de phishing de plus ? » | Non. La scène salarié montre l’avertissement au moment du geste ; la scène agent montre la retenue d’un appel d’outil. Les deux arrivent dans le même dossier SOC. |
| « L’agent a-t-il vraiment été piraté ? » | Le contenu hostile et le parcours de la passerelle sont exécutés localement, mais le cerveau de la démo est scripté pour rester reproductible. Nous ne revendiquons pas un taux de réussite d’attaque sur des modèles réels. |
| « Pourquoi autoriser “reprendre” ? » | L’analyste choisit après lecture de la chaîne. La reprise libère l’appel retenu dans le scénario ; un appel hors droits reste bloqué. « Couper » arrête la session et révoque le jeton. |
| « Une fuite a-t-elle eu lieu ? » | Sur “couper”, aucun rapport ne part. Sur “reprendre”, seul le rapport fictif est écrit localement. La console et les exports doivent distinguer tentative, blocage et exécution. |
| « Êtes-vous conformes à NIS2, OWASP ou MITRE ? » | Non. Le brouillon NIS2 aide à relire les faits, sans qualification ni envoi réglementaire. OWASP Agentic, ATLAS et ATT&CK servent de repères techniques ; leurs correspondances ne sont pas une certification. |

## Réalisé et cible

**Aujourd’hui :** gestes salariés simulés, agent et outils locaux, passerelle, décisions SOC, boîte noire, backend local, exports. **Après le hackathon :** capteur de poste autorisé, intégrations messagerie et agents déployés, gestion des identités, rétention et essais sur des données indépendantes. Il n’y a pas de surveillance native du Mac ni de connexion Outlook/Gmail dans cette démo.

**Vérification au 10 octobre :** 154 tests réussis (backend 45, interne 35, poste 17, leurres 19, attaque 16, scripts de démo 22) ; `npm run build` passe pour la console. Ce sont des tests du prototype, pas une mesure de détection en production. Aucun taux du banc synthétique n’est présenté comme une performance produit.

Parcours et commandes : [guide de démo](DEMO.md). Périmètre et limites : [README](../README.md) et [plan de cadrage](PLAN_NILA_2026-10-10.md).
