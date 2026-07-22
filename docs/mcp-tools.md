# MCP Tools — spec

Chrysalide expose **4 tools MCP**. Tous sont non-bloquants côté Cerveau : les jobs s'exécutent en tâche de fond et le Cerveau poll.

## `chrysalide_start_task`

Démarre un nouveau job. Retourne immédiatement avec un `job_id`.

### Input

| Champ | Type | Requis | Défaut | Rôle |
|---|---|---|---|---|
| `goal` | string | oui | — | Consigne de feature, explicite et complète |
| `repo_path` | string | oui | — | Chemin absolu du repo cible (doit être un repo git) |
| `base_branch` | string | non | `main` | Branche de base pour créer le worktree |
| `constraints` | array of string | non | `[]` | Contraintes techniques libres (stack, style, deps interdites…) |
| `budget.max_iterations` | integer | non | 15 | Nombre max d'itérations de la boucle |
| `budget.max_wall_time_min` | integer | non | 30 | Timeout global en minutes |
| `budget.max_tokens_total` | integer | non | 500000 | Budget de tokens total (input+output) |
| `provider_override` | string | non | — | Force un provider pour ce job. Format `<provider>:<model>` |
| `allow_network` | boolean | non | false | Autorise l'accès réseau depuis la sandbox |

Exemple de `goal` bien formé : *"Implémente un cache LRU thread-safe dans `src/cache.py`, avec tests pytest dans `tests/test_cache.py`. Le cache doit exposer `get(key)`, `put(key, value)`, `clear()`."*

### Output

Retourne un objet contenant : `job_id` (identifiant unique préfixé `chrys_`), `status` (initial : `running`), `created_at` (timestamp ISO), `sandbox_path` (chemin du worktree créé).

### Erreurs

| Code | Raison |
|---|---|
| `INVALID_REPO` | `repo_path` n'est pas un repo git |
| `BRANCH_NOT_FOUND` | `base_branch` inexistante |
| `WORKTREE_EXISTS` | Un worktree existe déjà à cet emplacement |
| `PROVIDER_UNAVAILABLE` | Provider demandé non configuré |

## `chrysalide_get_status`

Retourne l'état courant d'un job. Non-bloquant.

### Input

Un seul champ requis : `job_id`.

### Output

Retourne un objet contenant :

- `job_id` (echo).
- `status` — une valeur parmi `pending`, `running`, `done`, `failed`, `cancelled`, `escalated`.
- `progress` — objet avec `current_iteration`, `max_iterations`, `current_phase` (PLAN, ACT, VALIDATE, CORRECT), `wall_time_sec`.
- `last_finding` — le dernier finding émis, avec timestamp, type, résumé.
- `report_ready` — booléen, passe à `true` uniquement quand `status ∈ { done, failed, cancelled, escalated }`.

### Erreurs

| Code | Raison |
|---|---|
| `JOB_NOT_FOUND` | `job_id` inconnu |

## `chrysalide_get_report`

Retourne le rapport final. À appeler seulement quand `status.report_ready == true`.

### Input

| Champ | Type | Requis | Défaut | Rôle |
|---|---|---|---|---|
| `job_id` | string | oui | — | L'identifiant du job |
| `format` | string | non | `both` | `json`, `markdown`, ou `both` |

### Output

Selon le `format` :

- `json` : retourne uniquement le rapport JSON (voir [report-schema.md](report-schema.md)).
- `markdown` : retourne uniquement une version markdown lisible.
- `both` : retourne les deux dans un objet unique.

### Erreurs

| Code | Raison |
|---|---|
| `JOB_NOT_FOUND` | `job_id` inconnu |
| `REPORT_NOT_READY` | Le job est encore en cours |

## `chrysalide_cancel_task`

Annule un job en cours. La sandbox est **conservée** pour inspection.

### Input

| Champ | Type | Requis | Rôle |
|---|---|---|---|
| `job_id` | string | oui | L'identifiant du job à annuler |
| `reason` | string | non | Raison de l'annulation, journalisée |

### Output

Retourne un objet contenant : `job_id`, `status` (`cancelled`), `sandbox_path`, `partial_report_available` (booléen). Si `partial_report_available` vaut `true`, `chrysalide_get_report` peut être appelé pour lire ce qui a été fait avant l'annulation.

### Erreurs

| Code | Raison |
|---|---|
| `JOB_NOT_FOUND` | `job_id` inconnu |
| `JOB_ALREADY_DONE` | Job déjà terminé, rien à annuler |

## Format des erreurs

Toute réponse d'erreur MCP suit le pattern suivant : un champ `error` contenant un `code` (string identifiant standardisé), un `message` (description humaine), et un objet `details` avec le contexte spécifique.

## Notes d'implémentation

- Utiliser le SDK Python `mcp` officiel.
- Tous les tools sont exposés en async.
- Le serveur maintient un pool de jobs actifs en mémoire, avec persistance SQLite en parallèle.
- Un healthcheck implicite : appeler `chrysalide_get_status` sur un `job_id` inexistant retourne l'erreur `JOB_NOT_FOUND` proprement.
