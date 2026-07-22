# Agent Tools

Les outils disponibles pour l'Agent. **Aucun autre outil n'est accessible.**

Chaque outil est exposé au LLM via le mécanisme natif de function calling / tool use du provider (OpenAI, Anthropic, etc). L'implémenteur fait le mapping entre le format spécifique du provider et l'API interne unifiée.

## Famille `fs` — système de fichiers

### `fs.read`

Lit un fichier dans la sandbox.

- Entrée : un chemin relatif ou absolu, qui doit résoudre à un chemin **à l'intérieur de la sandbox**.
- Sortie : le contenu du fichier.
- Erreurs : `SandboxViolation` si le chemin est hors sandbox, `FileNotFoundError` si le fichier n'existe pas.

### `fs.write`

Crée ou remplace un fichier dans la sandbox.

- Entrée : un chemin (dans la sandbox) et un contenu.
- Sortie : un objet avec le chemin, le nombre de lignes, le hash SHA-256, la taille en octets.
- Erreurs : `SandboxViolation` si hors sandbox, `FileTooLarge` si dépassement de `max_file_size_mb`.

### `fs.list`

Liste les fichiers dans un dossier de la sandbox.

- Entrée : un chemin (dans la sandbox), un flag `recursive` optionnel.
- Sortie : une liste d'entrées avec nom, type (fichier / dossier), taille.

## Famille `shell` — commandes système

### `shell.exec`

Exécute une commande shell **whitelistée**.

- Entrée : la commande à exécuter (comme string), un timeout (défaut 60 secondes).
- Sortie : un objet avec `exit_code`, `stdout`, `stderr`, `duration_sec`.
- Erreurs : `CommandNotAllowed` si la commande ne matche aucun pattern de la whitelist, `CommandTimeout` si le timeout est dépassé.

### Whitelist par défaut

Commandes autorisées en pattern-matching (voir `allowed_commands.yaml`) :

- Compilation / parse : `python -m py_compile *`, `node --check *`, `go vet ./...`, `cargo check`.
- Tests : `pytest *`, `python -m pytest *`, `npm test`, `go test ./...`, `cargo test`.
- Lint : `ruff check *`, `mypy *`, `npm run lint`.
- Format check : `black --check *`, `prettier --check *`.

### Interdits toujours

Même avec `allow_network=true`, restent interdits :

- Toute commande destructive hors sandbox (`rm`, `mv`, `cp` sur des chemins non-sandbox).
- `sudo`, `chmod`, `chown`.
- Shell libre sans commande spécifique (`bash`, `sh`, `zsh`).
- Pipes, redirections, chaînages (`|`, `>`, `<`, `&&`, `;`). Chaque appel `shell.exec` doit être une invocation unique.

### Interdits par défaut, débloqués par `allow_network`

- `pip install`, `npm install`, `poetry add`, `cargo add`.
- `curl`, `wget`.
- `git fetch`, `git pull`, `git push`.

## Famille `git` — inspection du worktree

### `git.status`

Retourne l'état courant du worktree : listes des fichiers modifiés, créés, supprimés.

### `git.diff`

Retourne le diff complet du worktree ou d'un fichier spécifique. Utile en fin de boucle pour émettre le `diff_summary` dans le rapport.

## Famille `report` — journalisation et escalade

### `report.emit_finding`

Ajoute un finding structuré au journal de l'itération courante. L'Agent doit émettre un finding pour chaque action significative.

**Types de findings attendus** :

| type | champs requis |
|---|---|
| `plan` | `content` (le plan JSON) |
| `file_write` | `path`, `lines`, `hash`, `action` |
| `file_read` | `path`, `size_bytes` |
| `command_run` | `cmd`, `exit_code`, `stdout_tail`, `stderr_tail`, `duration_sec` |
| `decision` | `topic`, `choice`, `reason` |
| `correction_hypothesis` | `target_file`, `issue`, `fix` |
| `note` | `message` |

### `report.escalate`

Escalade vers l'Architecte et sort de la boucle immédiatement.

- Entrée : une `reason` (obligatoire, courte) et un `detail` (optionnel, plus long).
- Effet : marque le job comme `escalated` et crée automatiquement un blocker dans le rapport final.

**Cas d'usage typiques** :

- Ambiguïté irréductible dans le goal (ex : deux stratégies possibles, spec incomplète).
- Impossibilité technique (ex : dépendance manquante et `allow_network=false`).
- Boucle de correction sans progrès (mêmes erreurs 3 fois de suite).

## Ce qui n'est PAS un outil de l'Agent

Points d'attention pour l'implémenteur — ne pas ajouter ces outils sans design review :

- Pas d'`http.request`. L'Agent ne fait pas de requêtes web.
- Pas d'`env.get`. Pas d'accès aux variables d'environnement de l'hôte.
- Pas de `db.query`. Pas d'accès à des bases de données.
- Pas de `mcp.call`. L'Agent n'est pas un client MCP lui-même.
- Pas de `python.exec` / `eval`. Pas d'exécution de code dynamique arbitraire.

## Exposition aux providers

Chaque outil est traduit dans le format de tool-use du provider utilisé :

- **OpenAI / Azure** : format `tools` (function calling) avec `parameters` en JSON Schema.
- **Anthropic** : format `tools` (tool use) avec `input_schema` en JSON Schema.
- **Gemini** : `function_declarations`.
- **Ollama** : format spécifique aux modèles supportant tool use (Qwen2.5-coder, Llama 3.1+).

L'implémenteur maintient une interface interne unifiée pour éviter la duplication : une seule déclaration d'outil, plusieurs adaptateurs pour la génération des schémas provider-side.

## Tests

Voir [testing.md](testing.md). Tests unitaires critiques sur les outils :

- `fs.write` refuse un chemin hors sandbox.
- `fs.write` refuse un contenu qui dépasse la limite de taille.
- `shell.exec` refuse une commande hors whitelist.
- `shell.exec` respecte le timeout.
- `report.escalate` termine bien la boucle et crée le blocker.
