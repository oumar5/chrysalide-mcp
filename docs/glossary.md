# Glossary

Vocabulaire du projet. À lire avant les autres docs si les termes ne sont pas familiers.

## Cerveau

Le modèle principal qui tourne dans l'IDE de l'utilisateur (Claude Code, Antigravity, Cursor…). Il **planifie** au niveau macro, **valide** les rapports rendus par Chrysalide, et **décide** de l'intégration finale. Le Cerveau n'écrit pas de code dans le cadre de Chrysalide — il déclenche des jobs et lit des rapports.

## Architecte

Synonyme conceptuel du Cerveau, utilisé quand on veut insister sur le rôle de supervision. L'Architecte donne les instructions et valide, il ne code pas spontanément — mais peut être appelé en dernier recours si un Agent escalade.

## Agent

Le modèle qui tourne à l'intérieur de Chrysalide et exécute la boucle plan → act → validate → correct. Il vit dans une sandbox, produit du code, exécute des tests, et rend un rapport. Il utilise un modèle plus économique que le Cerveau (GPT-4o-mini, Claude Haiku, ou un modèle local comme Qwen2.5-coder).

## Job

Une exécution complète de Chrysalide déclenchée par un appel `chrysalide_start_task`. Un job a un `job_id` unique, un état (`pending`, `running`, `done`, `failed`, `cancelled`, `escalated`), une sandbox associée, et produit un rapport final.

## Sandbox

L'environnement isolé dans lequel l'Agent travaille. En v1, c'est un git worktree créé sur une branche jetable `chrysalide/<job_id>`. En v2, un conteneur Docker. La sandbox est **conservée** après le job pour permettre l'inspection par l'utilisateur.

## Worktree

Un checkout git secondaire qui partage le même `.git` que le repo principal, mais expose un espace de travail physiquement séparé. Utilisé comme mécanisme de sandbox v1. Créé avec `git worktree add`, supprimé avec `git worktree remove`.

## Finding

Un événement structuré émis par l'Agent pendant son exécution. Un finding a un type (`plan`, `file_write`, `command_run`, `decision`, `correction_hypothesis`, `note`) et des champs associés. Les findings sont agrégés dans le rapport final.

## Rapport (Report)

Le résultat final d'un job, structuré en JSON avec version markdown. Contient : goal, status, plan, files_changed, commands_executed, decisions, blockers, tokens_used, sandbox_path, integration_hint. C'est le **seul artefact** que le Cerveau consomme.

## Boucle (Agent Loop)

La séquence répétée par l'Agent : PLAN → ACT → VALIDATE → CORRECT. Bornée par `max_iterations`, `max_wall_time_min`, `max_tokens_total`. Se termine par succès (tous les critères passent) ou escalade.

## Phase

L'une des 4 étapes de la boucle. Chaque phase a un prompt dédié et un rôle précis :

- **PLAN** : décomposer la consigne en sous-tâches et lister les commandes de validation.
- **ACT** : écrire ou modifier des fichiers dans la sandbox.
- **VALIDATE** : exécuter les commandes de validation.
- **CORRECT** : analyser les échecs et proposer une correction.

## Escalade (Escalate)

Quand l'Agent renonce à finir un job en autonomie et signale un blocage. Se fait via `report.escalate` ou automatiquement quand un budget est dépassé ou qu'une boucle d'erreurs est détectée. Le rapport final a `status = "escalated"` et contient un blocker explicite. Le Cerveau décide alors : ré-instruire, clarifier, ou reprendre la main.

## Blocker

Un blocage rencontré pendant un job. Peut être `resolved` (l'Agent a fini par contourner), `escalated` (renvoyé au Cerveau), ou `unresolved` (le job s'est arrêté sans résolution). Toujours présent dans le rapport quand le job n'est pas un succès pur.

## Provider

Un adaptateur LLM. Chrysalide supporte OpenAI, Anthropic, Google Gemini, Ollama (local), Azure OpenAI. Tous exposent la même interface interne (`WorkerProvider.complete`).

## Budget

Les limites hard d'un job : `max_iterations` (défaut 15), `max_wall_time_min` (défaut 30), `max_tokens_total` (défaut 500 000). Dépassement → escalade automatique.

## Anti-optimisme

Ensemble de défenses contre le failure mode "l'Agent déclare fini alors qu'il a triché" : interdiction des stubs, interdiction de désactiver des tests, rapports contenant les stdout bruts, décisions explicites. Voir [agent-loop.md](agent-loop.md).

## Whitelist (commandes)

La liste des patterns de commandes shell autorisées à s'exécuter via `shell.exec`. Définie dans `allowed_commands.yaml`. Toute commande hors whitelist est refusée. Voir [agent-tools.md](agent-tools.md).

## Architecture étoile

Modèle d'organisation multi-agents où un superviseur unique (le Cerveau / Architecte) parle à N agents en parallèle. Contraste avec l'architecture hiérarchique (superviseur → mini-superviseur → agents), rejetée par ce projet parce qu'empiriquement moins performante.

## Failure mode

Un mode de défaillance récurrent. Le failure mode principal des systèmes agentiques est le rapport optimiste (déclarer "fini" alors qu'on a triché ou stubbed). Chrysalide met plusieurs défenses en couches contre ce mode.

## Ligne rouge

Une contrainte non-négociable du design. Chrysalide en a plusieurs : jamais d'écriture hors sandbox, jamais de commande hors whitelist, jamais de merge automatique dans le repo utilisateur. Voir [security.md](security.md).

## Integration hint

Une chaîne de caractères dans le rapport final qui suggère à l'utilisateur la commande git à exécuter pour intégrer le travail dans son repo (typiquement un `git merge chrysalide/<job_id>`). Jamais exécutée automatiquement.
