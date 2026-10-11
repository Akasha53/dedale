# Banc d'essai sAIfe

Une page web pour conduire sAIfe depuis un navigateur, sans ligne de commande. Tout tourne
sur `127.0.0.1`.

```bash
./banc/demarrer.sh          # sert la page sur http://127.0.0.1:8900 (BANC_PORT pour en changer)
```

Le serveur (`serveur.py`, bibliothèque standard, lancé avec le python3 du système) sert la page
et expose des endpoints qui lancent les vraies commandes du dépôt en sous-processus. Le jeton
analyste est lu côté serveur dans `~/.config/dedale/` et ajouté aux appels au backend ; il
n'apparaît jamais dans la page servie.

## Ce que fait chaque bouton

1. **Démarrer tout** — vérifie et lance ce qui manque : backend (8700), console SOC (5173),
   boîte mail et verdicts (8716/8717/8715). L'app Mac (8712) n'est jamais relancée, son état
   est seulement lu. Un voyant par service.
2. **Ouvrir** — console SOC, espace de validation finance, boîte mail d'Orbis.
3. **Bouclier du poste** — montre que l'app Mac lit la vraie config MCP du poste (serveurs vus,
   à risque), avec un lien vers la console.
4. **Côté salarié** — un bouton par cas de mail de test (`messagerie/envoyer_demo.py`), déposé
   dans la boîte. La pop-up du bouclier arrive à l'écran.
5. **Boîte d'Orbis** — les mails présents, avec le verdict de sAIfe (sûr, suspect, frauduleux).
6. **Agent IA** — lance un vrai agent piloté par un modèle local Ollama (gpt-oss:20b par défaut,
   qwen2.5:7b au choix) sur la vraie boîte, contre le vrai backend 8700. Le flux est montré en
   direct : outils appelés, « retenu » et « coupé ». L'incident apparaît dans la console SOC.
7. **Virements** — un virement normal (rien ne s'affiche) et un virement vers un RIB changé
   (pop-up « Retenu »), via `/avertir` de l'app Mac.
8. **Repartir propre** — sauvegarde la base du backend dans `data/sauvegardes/`, puis repart
   d'une base vide, comme `./demo.sh jury`.
9. **Journal en direct** — incidents et fil des agents lus au backend, plus les actions du banc.

## Limite connue

L'agent de la section 6 est un vrai modèle, pas un script. Les petits modèles locaux sont
prudents : ils tombent sur le mail piégé et appellent de vrais outils, ce qui ouvre un incident
« comportement inhabituel » dès qu'ils sortent de leur inventaire, mais ils ne suivent pas
toujours la consigne cachée qui mènerait à la coupure pour exfiltration. Le parcours
« retenu puis coupé » complet est fiable avec le cerveau Haiku (`docs/REEL_OU_SIMULE.md`).
