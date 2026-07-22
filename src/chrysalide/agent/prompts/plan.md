Tu es dans la phase PLAN.
Objectif : {goal}
Contraintes : {constraints}

Décompose cet objectif en sous-tâches techniques, et identifie les commandes de validation à exécuter pour s'assurer que le code fonctionnera (par ex: `pytest`, `npm test`, `flake8`). Identifie aussi les risques.

Appelle l'outil `submit_plan` avec :
- subtasks : liste de sous-tâches (titre, fichiers concernés)
- validation_commands : liste de commandes shell de validation
- risks : liste de risques
