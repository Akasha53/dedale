# Contrôle local des secrets

Depuis la racine du dépôt :

```sh
python3 scripts/scan_secrets.py --self-test
python3 scripts/scan_secrets.py
```

Le script n'utilise que Python et Git. Il examine les fichiers suivis ou non ignorés présents, puis les versions de fichiers et les messages de commit accessibles depuis toutes les références Git locales. Il cherche des formats de clés courants (AWS, GitHub, OpenAI, Anthropic, Google, Slack, Stripe), des clés privées, des JWT et des affectations suspectes. Le rapport donne la catégorie, le fichier et la ligne, jamais la valeur. Le code de sortie vaut `0` sans alerte, `1` si une vérification manuelle est nécessaire, `2` si le scan a échoué.

Contrôle du 10 octobre 2026, sur `18e98b4` et les modifications locales : 157 fichiers présents et 290 objets historiques examinés ; 6 alertes dans les fichiers présents et 12 dans l'historique. Elles se trouvent dans `backend/tests/test_humain.py`, `poste/tests/test_garde.py` et `poste/garde/simulateur.py`. Ces emplacements contiennent des scénarios de détection ; le scanner les signale tout de même. Aucun de ces résultats ne prouve qu'une clé est active. Vérifier les valeurs en local avant publication ; si une clé réelle est découverte, la révoquer et examiner son historique Git sans la copier dans un ticket.

Le contrôle ne lit pas les fichiers ignorés par Git, dont `.env` et les bases locales. Il saute les fichiers binaires, les liens symboliques et les fichiers de plus de 1 Mo. Il ne voit que les références Git disponibles sur cette machine et les formats prévus par ses règles ; un résultat sans alerte ne garantit donc pas l'absence de secret. Un scanner dédié et une revue des fichiers livrés restent utiles avant une diffusion publique.
