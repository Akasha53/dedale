# Démonstration de Dédale

Ce parcours relie le garde du poste, l'agent interne, le backend et la console SOC. Orbis Pay, les mails, les secrets, les rapports et les paiements sont fictifs. L'agent utilise un cerveau scripté : la scène reste reproductible sans appeler un modèle.

## Préparer les deux terminaux

À la racine du dépôt, lancez les services :

```bash
./lancer.sh
```

Le backend répond sur `http://127.0.0.1:8700` et la console sur `http://127.0.0.1:5173`. Le lanceur refuse de démarrer si les ports 8700, 8701, 8711 ou 5173 sont occupés. Il ne ferme pas les processus déjà présents. Gardez ce terminal ouvert.

Dans un second terminal :

```bash
./demo.sh
```

Le script vérifie le backend, enregistre les canaris nécessaires et crée des identifiants de session différents à chaque exécution. Il n'écrit pas dans `poste/demo/popup.html`. Il affiche les liens directs vers les incidents de cette exécution. Si la base contient d'anciens journaux incomplets, le backend se déclare dégradé : le script le signale et continue, car il ne lit que ses propres sessions. Une erreur d'écriture SQLite l'arrête.

## Jouer les scènes

1. Camille reçoit un mail qui usurpe Orbis Pay. Le garde du poste affiche l'avertissement dans le terminal. Saisissez `annuler` ou `continuer` ; une entrée vide ne choisit rien. Avec `annuler`, le journal garde l'avertissement, mais aucun incident n'est ouvert pour ce geste. Avec `continuer`, un incident `humain_phishing` apparaît dans la partie salariés de la console. Cette décision ne coupe pas le poste.
2. L'agent interne lit un mail contenant une consigne cachée, puis tente un appel d'outil sortant. La passerelle retient cet appel et le script affiche l'identifiant de l'incident ainsi que son lien. Ouvrez ce lien dans la console, dans la partie agents IA, et examinez la chaîne avant de choisir. Le script attend votre décision ; il n'en envoie aucune lui-même.
3. Choisissez `Couper` pour arrêter l'agent et révoquer son jeton. Aucun rapport fictif ne part. Pour montrer l'autre issue, relancez `./demo.sh` et choisissez `Reprendre` sur le nouvel incident : l'appel retenu s'exécute alors et un rapport fictif apparaît dans la boîte d'envoi locale de cette exécution. Il n'est envoyé à personne.

Le choix `continuer` du salarié et la décision `Reprendre` de l'analyste sont deux actes différents. Le premier ouvre l'incident humain ; le second libère un appel d'outil de l'agent.

## Variantes

```bash
./demo.sh --choix-salarie continuer --attente 180
./demo.sh --choix-salarie annuler --avec-mcp --avec-droits
```

`--choix-salarie` évite la saisie interactive pour enregistrer la démo. `--attente` fixe le délai maximal, en secondes, pour chaque décision SOC. Avec `--avec-mcp`, une deuxième scène d'agent montre une consigne cachée dans la description d'un outil MCP ; il faut prendre une nouvelle décision dans la console. Avec `--avec-droits`, l'agent tente un paiement hors du jeton de sa tâche. La passerelle bloque localement cette opération et révoque le jeton. L'incident reste ouvert pour examen ; ce scénario ne simule pas une décision de l'analyste.

Pour un backend démarré sur un autre port, passez son adresse avec `--backend`. `--console` règle seulement le lien affiché : la console doit elle-même communiquer avec ce backend. La console Vite fournie par le dépôt pointe, en développement, vers le port 8700.

```bash
./demo.sh --backend http://127.0.0.1:8700 --console http://127.0.0.1:5173
```

## Contrôler les traces

Remplacez les identifiants ci-dessous par ceux que le script affiche :

```bash
curl -s http://127.0.0.1:8700/api/sessions/ID-DE-SESSION
curl -s http://127.0.0.1:8700/api/incidents/INC-0001
curl -s http://127.0.0.1:8700/api/incidents/INC-0001/export?format=ecs
curl -s http://127.0.0.1:8700/api/incidents/INC-0001/nis2
```

La session contient les événements ; l'incident contient la chaîne et les décisions. L'export NIS2 est un brouillon à qualifier par un humain, sans transmission automatique. Les taux du banc de mesure concernent son trafic synthétique, pas ces quelques scènes.

Si le backend est inaccessible, le script s'arrête avant les scènes avec le code de sortie 2. Si une décision tarde trop, il sort avec le code 3 : l'appel retenu n'est pas exécuté et l'incident reste à traiter. `Ctrl-C` arrête la démo avec le code 130 sans libérer l'appel. Une nouvelle exécution reçoit de nouveaux identifiants ; elle ne reprend pas l'appel précédent.
