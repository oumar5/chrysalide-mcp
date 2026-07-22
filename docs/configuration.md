# Configuration

Chrysalide se configure via trois sources, dans l'ordre de priorité croissante :

1. Valeurs par défaut du code.
2. Fichiers YAML dans `config/` (`allowed_commands.yaml`, `sandbox_config.yaml`).
3. Variables d'environnement (fichier `.env` ou env système).
4. Arguments par job passés dans `chrysalide_start_task`.

L'implémentation utilise `pydantic-settings` pour centraliser.

## Variables d'environnement principales

### Clés API providers

| Variable | Rôle | Obligatoire |
|---|---|---|
| `OPENAI_API_KEY` | Clé OpenAI | Si provider = openai |
| `ANTHROPIC_API_KEY` | Clé Anthropic | Si provider = anthropic |
| `GEMINI_API_KEY` | Clé Google Gemini | Si provider = gemini |
| `AZURE_OPENAI_ENDPOINT` | Endpoint Azure | Si provider = azure |
| `AZURE_OPENAI_API_KEY` | Clé Azure | Si provider = azure |
| `AZURE_OPENAI_DEPLOYMENT` | Nom du deployment | Si provider = azure |
| `OLLAMA_BASE_URL` | URL Ollama | Non (défaut `http://localhost:11434`) |

### Configuration serveur

| Variable | Défaut | Rôle |
|---|---|---|
| `CHRYSALIDE_DEFAULT_PROVIDER` | `openai:gpt-4o-mini` | Provider primary utilisé si pas d'override par job |
| `CHRYSALIDE_FALLBACK_PROVIDER` | (aucun) | Provider fallback activé après retries épuisés |
| `CHRYSALIDE_STORE_PATH` | `~/.chrysalide/jobs.db` | Emplacement du store SQLite |
| `CHRYSALIDE_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `CHRYSALIDE_LOG_PATH` | `~/.chrysalide/logs/` | Dossier des logs |

### Budgets par défaut

Utilisés si le job n'en fournit pas.

| Variable | Défaut | Rôle |
|---|---|---|
| `CHRYSALIDE_MAX_ITERATIONS` | 15 | Boucle max |
| `CHRYSALIDE_MAX_WALL_TIME_MIN` | 30 | Timeout global |
| `CHRYSALIDE_MAX_TOKENS_TOTAL` | 500000 | Budget tokens |
| `CHRYSALIDE_MAX_FILE_SIZE_MB` | 1 | Limite par fichier |
| `CHRYSALIDE_SHELL_TIMEOUT_SEC` | 60 | Timeout par commande shell |

### Rétention

| Variable | Défaut | Rôle |
|---|---|---|
| `CHRYSALIDE_CLEANUP_AFTER_DAYS` | 7 | Nettoyage auto des worktrees anciens |
| `CHRYSALIDE_CLEANUP_ENABLED` | false | Active le nettoyage auto |

## Fichier `.env.example`

L'implémenteur fournit un fichier `.env.example` à la racine, listant toutes les variables ci-dessus commentées, avec des valeurs vides ou d'exemple. L'utilisateur copie vers `.env` et remplit.

## Fichier `allowed_commands.yaml`

Ce fichier définit la whitelist des commandes que `shell.exec` peut exécuter.

Structure attendue :

- Une clé `allowed` : liste de patterns (glob-like) autorisés en tout temps.
- Une clé `allowed_with_network` : patterns activés uniquement quand un job passe `allow_network=true`.
- Une clé `always_denied` : patterns interdits même si présents ailleurs (défense en profondeur).

Voir [agent-tools.md](agent-tools.md) section "Whitelist" pour la liste par défaut recommandée.

L'utilisateur peut personnaliser ce fichier, mais chaque ajout est sous sa responsabilité — un `bash -c *` ouvert casse toutes les défenses.

## Fichier `sandbox_config.yaml`

Ce fichier définit les paramètres de la sandbox.

Clés attendues :

| Clé | Défaut | Rôle |
|---|---|---|
| `backend` | `worktree` | `worktree` (v1) ou `docker` (v2) |
| `worktree_root` | `.chrysalide/worktrees` | Chemin racine des worktrees créés dans le repo utilisateur |
| `max_file_size_mb` | 1 | Duplique la variable env (par lisibilité) |
| `max_total_size_mb` | null | Limite totale, désactivée par défaut |
| `env_whitelist` | `[PATH, HOME, LANG, LC_ALL]` | Variables d'env transmises aux subprocess |
| `docker_image` | (v2 uniquement) | Image runtime pour Sandbox v2 |
| `docker_memory_limit` | (v2 uniquement) | Limite RAM du conteneur |
| `docker_cpu_limit` | (v2 uniquement) | Limite CPU du conteneur |

## Configuration par job

Certains paramètres se règlent au niveau du job dans `chrysalide_start_task`, indépendamment de la config globale :

- `provider_override` — surcharge du provider pour ce job.
- `budget.max_iterations`, `budget.max_wall_time_min`, `budget.max_tokens_total` — budgets spécifiques.
- `allow_network` — active les commandes réseau pour ce job.
- `constraints` — contraintes techniques (stack, style) injectées dans le prompt.

## Ordre de résolution — exemple

Pour `max_iterations` :

1. Le code a une valeur par défaut interne (15).
2. Si `CHRYSALIDE_MAX_ITERATIONS=20` est dans `.env`, cette valeur remplace le défaut.
3. Si le job passe `budget.max_iterations=10`, cette valeur remplace tout.

Le résultat final est 10.

## Validation

Au démarrage du serveur :

- Vérifier la présence des clés API pour les providers déclarés en primary/fallback.
- Vérifier que `store_path` est accessible en écriture.
- Vérifier que les fichiers YAML sont parsables.
- Vérifier que `worktree_root` est un chemin relatif (pas absolu).

Échec de validation → sortie propre avec un message clair, pas de démarrage silencieux dégradé.

## Configuration pour tests

En environnement de test, un fichier `.env.test` peut être utilisé avec des clés API mockées et des budgets réduits (par exemple `MAX_ITERATIONS=3`). Voir [testing.md](testing.md).
