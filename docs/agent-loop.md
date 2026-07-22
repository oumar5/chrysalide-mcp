# Agent Loop

## Vue d'ensemble

L'Agent tourne dans une boucle plan → act → validate → correct jusqu'à succès ou abandon. Chaque itération produit des findings qui sont agrégés en rapport final.

```text
┌──────┐   ┌─────┐   ┌──────────┐   ┌─────────┐
│ PLAN │ → │ ACT │ → │ VALIDATE │ → │ CORRECT │ → retour à ACT
└──────┘   └─────┘   └──────────┘   └─────────┘
   │                       │
   │                       └── tous les critères passent → SUCCESS
   │
   └── plan invalide → ESCALATE
                                 max_iter ou blocker persistant → ESCALATE
```

## Les 4 phases

### PLAN — décomposition initiale

Appelée une seule fois au début du job.

**Entrée** : le goal fourni par le Cerveau + les constraints éventuelles.

**Sortie attendue de l'Agent** : un plan structuré (JSON) contenant :

- Une liste de sous-tâches (id, description, fichiers concernés).
- Une liste de commandes de validation à exécuter à la fin (par exemple : compilation, tests, lint).
- Une liste de risques identifiés (par exemple : cas limites, dépendances externes).

**Finding émis** : de type `plan`, contenant le plan complet.

### ACT — écriture de code

Appelée à chaque itération.

**Entrée** : le plan courant + les findings précédents (surtout les erreurs de VALIDATE si on est en itération >1).

**Comportement** : l'Agent utilise l'outil `fs.write` pour créer ou modifier des fichiers dans la sandbox. Il peut appeler `fs.read` pour relire un fichier avant modification.

**Anti-optimisme critique** : le prompt d'ACT interdit explicitement de produire du code incomplet — pas de `TODO`, pas de `pass`, pas de `raise NotImplementedError`, pas de stub vide. Si l'Agent ne sait pas comment implémenter, il doit appeler `report.escalate` au lieu de tricher.

**Finding émis** : un par fichier écrit, avec path, nombre de lignes, hash, action (created / modified).

### VALIDATE — exécution des critères

Appelée après chaque ACT.

**Entrée** : la liste `validation_commands` du plan.

**Comportement** : l'Agent exécute chaque commande via `shell.exec`, capture stdout, stderr, exit code, durée.

**Critère de succès** : **toutes** les validation_commands retournent exit 0.

- Si succès complet : émet un finding `validation_success` et sort de la boucle.
- Si au moins une commande échoue : passe à CORRECT.

**Finding émis par commande** : de type `command_run`, avec cmd, exit_code, stdout_tail, stderr_tail, duration_sec.

### CORRECT — analyse et re-plan local

Appelée si VALIDATE a échoué.

**Entrée** : les findings de la dernière VALIDATE (surtout les stdout/stderr des commandes qui ont échoué).

**Comportement** : l'Agent produit une hypothèse de correction ciblée et retourne à ACT. Le prompt lui demande d'identifier la cause précise de l'échec, PAS de tout réécrire.

**Si la cause n'est pas identifiable** : escalade.

**Finding émis** : de type `correction_hypothesis`, avec target_file, issue, fix proposé.

## Boucle et critères d'arrêt

### Succès

Tous les critères de VALIDATE passent → rapport final `status = "success"`.

### Escalade

Déclenchée dans les cas suivants :

- L'Agent appelle explicitement `report.escalate` avec une raison.
- Détection de boucle : les mêmes signatures d'erreur reviennent 3 itérations d'affilée (comparaison de hashes des sorties d'erreur).
- `max_iterations` atteint sans succès.
- `max_wall_time_min` atteint.
- `max_tokens_total` atteint.

Le rapport final a `status = "escalated"` avec un ou plusieurs blockers détaillés.

### Échec inattendu

Exception non gérée dans l'orchestrator ou provider indisponible après retries → `status = "failed"` avec un objet `error` dans le rapport.

## Anti-optimisme — le point critique

Le rapport optimiste (agent qui déclare "fini" alors qu'il a triché) est le failure mode principal des systèmes agentiques. Défenses en couches :

1. **Interdiction de désactiver silencieusement des tests.** Le prompt de CORRECT refuse l'ajout de `@pytest.mark.skip` ou la suppression de tests. Une commande de validation additionnelle peut vérifier que le nombre de tests ne décroît pas.

2. **Interdiction des stubs.** Le prompt d'ACT refuse `pass`, `raise NotImplementedError`, `# TODO`. Un check regex sur le diff final refuse ces marqueurs.

3. **Le rapport contient les stdout bruts**, pas des résumés. Le Cerveau peut détecter les mensonges en scannant.

4. **Les décisions sont explicites.** L'Agent doit émettre un finding de type `decision` pour chaque choix non-trivial (choix de lib, choix d'algo, choix de structure).

5. **Le statut `success` n'est déclaré que si TOUS les critères passent.** Pas de "success partiel" implicite. Si un critère échoue, le statut est `partial` ou `escalated`.

## Prompts — structure de référence

Chaque phase a un prompt dédié, matérialisé par un fichier markdown avec placeholders interpolés à l'exécution. Le prompt système commun (`agent_system.md`) énonce les règles :

- Ne jamais modifier de fichiers hors sandbox.
- Ne jamais utiliser des commandes hors whitelist.
- Ne jamais prétendre qu'une tâche est finie si elle ne l'est pas.
- Ne jamais ajouter de stubs, TODO, ou tests désactivés.
- Ne jamais appeler des APIs externes sauf si `allow_network=true`.
- Toujours émettre un finding pour chaque action significative.
- Toujours justifier les décisions non-triviales.
- Toujours escalader plutôt que produire du code incorrect.
- Toujours utiliser les outils fournis, jamais autre chose.

Les prompts spécifiques par phase (`plan.md`, `act.md`, `validate.md`, `correct.md`) sont à rédiger par l'implémenteur. Ils prennent des placeholders comme `{goal}`, `{plan}`, `{findings}`, `{errors}` interpolés à l'exécution.

## État interne de l'Agent

Pendant la boucle, l'Agent maintient un état minimal en mémoire :

- Le goal courant et les contraintes.
- Le plan produit par PLAN.
- La liste des findings accumulés.
- L'itération courante.
- Le compteur de tokens utilisés.
- Les signatures d'erreurs déjà vues (pour la détection de boucle).

Cet état est passé de phase en phase et remis à zéro entre deux jobs.

## Tests de la boucle

Voir [testing.md](testing.md). La boucle est testable en unit avec un provider stubbé qui retourne des réponses scriptées, sans dépendre d'un LLM réel. Chaque scénario (success au premier essai, échec puis correction, escalade sur boucle) a un test dédié.
