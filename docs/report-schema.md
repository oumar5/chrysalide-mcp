# Report Schema

## Principe

Le rapport final est le **seul artefact que le Cerveau consomme**. Il doit être :

- **Structuré** : format JSON stable, versionné.
- **Vérifiable** : contient les stdout bruts, les hashes de fichiers, la liste exhaustive des commandes exécutées.
- **Lisible en parallèle** : une version markdown lisible est générée pour un survol humain.

## Champs du rapport JSON

| Champ | Type | Requis | Description |
|---|---|---|---|
| `job_id` | string | oui | Identifiant unique du job, pattern `chrys_<slug>` |
| `status` | string | oui | Un parmi `success`, `partial`, `escalated`, `failed`, `cancelled` |
| `summary` | string | oui | Résumé humain court (2-3 phrases) |
| `goal` | string | oui | La consigne d'origine (echo pour traçabilité) |
| `created_at` | ISO datetime | oui | Timestamp du début du job |
| `completed_at` | ISO datetime | oui | Timestamp de fin du job |
| `iterations_used` | integer | oui | Nombre d'itérations effectuées |
| `iterations_max` | integer | oui | Budget d'itérations initial |
| `wall_time_sec` | number | oui | Durée totale du job |
| `tokens_used` | object | oui | Objet avec `input`, `output`, `total` |
| `provider` | object | oui | Objet avec `name` et `model` utilisés |
| `plan` | object | non | Le plan produit par la phase PLAN (subtasks, validation_commands, risks) |
| `files_changed` | array | oui | Liste des fichiers modifiés (voir sous-schéma) |
| `diff_summary` | object | oui | `files`, `added`, `removed` |
| `commands_executed` | array | oui | Liste des commandes exécutées (voir sous-schéma) |
| `decisions` | array | non | Liste des décisions non-triviales prises par l'Agent |
| `blockers` | array | non | Liste des blocages, résolus ou escaladés |
| `iteration_log` | array | non | Journal détaillé de chaque itération |
| `sandbox_path` | string | oui | Chemin de la sandbox conservée |
| `integration_hint` | string | non | Commande git suggérée pour intégrer, ou null |
| `error` | object | non | Présent uniquement si `status == failed` |

## Sous-schémas

### `files_changed[]`

| Champ | Type | Rôle |
|---|---|---|
| `path` | string | Chemin relatif dans la sandbox |
| `action` | string | `created`, `modified`, `deleted` |
| `lines` | integer | Nombre de lignes final |
| `hash` | string | `sha256:<64 hex chars>` du contenu |
| `size_bytes` | integer | Taille en octets |

### `commands_executed[]`

| Champ | Type | Rôle |
|---|---|---|
| `phase` | string | `VALIDATE` ou `ACT_HELPER` |
| `iteration` | integer | Numéro d'itération où la commande a été exécutée |
| `cmd` | string | Commande complète exécutée |
| `exit_code` | integer | Code de retour |
| `duration_sec` | number | Durée d'exécution |
| `stdout_tail` | string | Fin du stdout, tronquée à 4000 caractères |
| `stderr_tail` | string | Fin du stderr, tronquée à 4000 caractères |
| `truncated` | boolean | True si la sortie a été tronquée |

### `decisions[]`

| Champ | Type | Rôle |
|---|---|---|
| `topic` | string | Sujet de la décision |
| `choice` | string | Le choix retenu |
| `reason` | string | Justification du choix |

### `blockers[]`

| Champ | Type | Rôle |
|---|---|---|
| `description` | string | Nature du blocage |
| `resolution` | string | `resolved`, `escalated`, ou `unresolved` |
| `detail` | string | Contexte additionnel, ce qui a été tenté |

### `error` (si failed)

| Champ | Type | Rôle |
|---|---|---|
| `type` | string | Nom d'exception ou catégorie d'erreur |
| `message` | string | Message humain |
| `traceback` | string | Stack trace complète (optionnel) |

## Règles de troncature

- Les champs `stdout_tail` et `stderr_tail` sont tronqués à 4000 caractères, en gardant la fin. Un booléen `truncated` indique si la troncature a eu lieu.
- Le champ `iteration_log` peut être volumineux. Deux options :
  - Inline si la taille totale du rapport reste sous 100 Ko.
  - Externalisé dans un fichier `.chrysalide/reports/<job_id>/iterations.json` avec un pointeur dans le rapport principal si > 100 Ko.

## Version markdown

Une version markdown lisible est générée en parallèle du JSON. Structure suggérée :

- Titre + statut + goal + durée + itérations + tokens.
- Section "Résumé" (le champ `summary`).
- Section "Fichiers modifiés" (une liste à puces).
- Section "Commandes exécutées" (un tableau avec cmd, exit, durée).
- Section "Décisions" (une liste à puces).
- Section "Blocages" si non vide.
- Section "Intégration" avec la commande git suggérée si `integration_hint` est présent.

## Contrat de compatibilité

Le rapport est versionné dans un champ `$schema` en haut du JSON (par exemple `https://chrysalide.dev/schemas/report/v1.json`). Toute évolution breaking incrémente la version. Les consommateurs (Cerveau) peuvent négocier une version via un futur champ `preferred_report_version` dans les appels `chrysalide_get_report`.

## Trois exemples de statuts

### success

Tous les critères de VALIDATE passent, aucun blocker. Le rapport contient un `integration_hint` (par exemple : `git merge chrysalide/<job_id>`).

### escalated

Au moins un critère n'a jamais passé, ou l'Agent a explicitement escaladé. Le rapport contient au moins un blocker avec `resolution = escalated`. `integration_hint` est `null` — le Cerveau doit décider.

### failed

Exception non gérée, provider indisponible, ou violation critique. Le rapport contient un objet `error` détaillé. Aucun `integration_hint`. Le job n'a probablement pas produit de code utilisable.
