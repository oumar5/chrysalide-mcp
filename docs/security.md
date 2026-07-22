# Security

Chrysalide donne à un LLM la capacité d'exécuter du code et d'écrire des fichiers. Cette page liste les défenses en couches.

## Menaces principales

| Menace | Description | Défense principale |
|---|---|---|
| Écriture hors sandbox | LLM tente d'écrire ailleurs que dans le worktree | Vérification stricte de tout chemin résolu contre le chemin du worktree |
| Exécution de commandes destructives | LLM tente `rm -rf`, `sudo`, etc | Whitelist stricte de commandes, pas de shell libre |
| Exfiltration de secrets | LLM lit `.env`, tokens, clés SSH | Env réduit dans les subprocess, pas de lecture hors sandbox |
| Appels réseau non autorisés | LLM installe des paquets, télécharge du code | `allow_network=false` par défaut, whitelist ne contient pas les commandes réseau |
| Consommation excessive | LLM boucle à l'infini | Budgets stricts : max_iterations, wall_time, tokens_total |
| Fichiers volumineux | LLM écrit un fichier de 10 Go | Limite de taille par fichier |
| Injection dans les prompts | Contenu de fichier utilisateur contient une injection | Système isolé, injection ne peut au pire que faire tourner en boucle (arrêtée par budgets) |
| Blocage silencieux | LLM produit du code cassé et déclare "fini" | Rapport structuré vérifiable, checks anti-optimisme |

## Défenses en couches

### 1. Sandbox obligatoire

Toute écriture est bornée à `.chrysalide/worktrees/<job_id>`. Toute tentative hors de ce chemin lève `SandboxViolation`, capturée par l'orchestrator. Voir [sandbox.md](sandbox.md).

### 2. Whitelist stricte de commandes

L'outil `shell.exec` refuse toute commande qui ne matche pas un pattern de `allowed_commands.yaml`. Pas de shell libre, pas de pipes, pas de redirections, pas de chaînages. Voir [agent-tools.md](agent-tools.md).

### 3. Environnement subprocess réduit

Quand `shell.exec` lance un subprocess, on part d'une env vide et on ne conserve qu'une whitelist explicite (par défaut : PATH, HOME, LANG, LC_ALL). Les variables sensibles (AWS, SSH, GitHub tokens, etc) ne sont **jamais** transmises.

### 4. Réseau off par défaut

- La sandbox v1 (git worktree) n'isole pas le réseau au niveau kernel, mais les commandes réseau sont absentes de la whitelist par défaut.
- La sandbox v2 (Docker) ajoute une isolation réseau réelle via `--network=none`.
- L'option `allow_network=true` dans un job ajoute les commandes réseau à la whitelist locale au job — jamais globalement.

### 5. Budgets stricts

Trois budgets hard, tous configurables au niveau du job :

- `max_iterations` (défaut 15) — arrêt de la boucle.
- `max_wall_time_min` (défaut 30) — arrêt par timeout global.
- `max_tokens_total` (défaut 500 000) — arrêt par consommation.

Dépassement d'un budget → escalade automatique avec blocker `budget_exceeded`.

### 6. Timeouts par commande

Chaque appel `shell.exec` a un timeout individuel (défaut 60 secondes). Dépassement → la commande est tuée, l'échec est reporté comme un finding.

### 7. Limite de taille par fichier

`fs.write` refuse tout contenu qui dépasse `max_file_size_mb` (défaut 1 Mo).

### 8. Aucune intégration automatique

Chrysalide ne fait jamais :

- `git push`, `git merge` sur le repo utilisateur.
- Modification directe d'un fichier hors sandbox.
- Envoi d'email, ping externe, télémétrie tierce.

L'intégration reste **manuelle et explicite** côté utilisateur.

### 9. Rapport vérifiable

Le rapport contient les stdout bruts et les hashes de fichiers. Le Cerveau peut détecter les mensonges (tests désactivés, code stubbed) en scannant le rapport, sans relire tout le code. Voir [agent-loop.md](agent-loop.md) section "Anti-optimisme".

### 10. Journalisation

Toutes les commandes exécutées, tous les fichiers écrits, toutes les décisions sont journalisés. En cas d'incident, le journal permet le forensics complet.

## Ce que Chrysalide NE protège PAS contre

Pour être honnête avec l'utilisateur :

- **Un utilisateur malveillant** qui écrit lui-même un `allowed_commands.yaml` ouvert peut se tirer une balle. La responsabilité de la whitelist reste à l'utilisateur.
- **Un provider LLM compromis** peut retourner n'importe quoi. Chrysalide ne signe pas cryptographiquement les réponses provider.
- **Une faille dans git ou dans Python** est en dehors du périmètre. Les mises à jour de sécurité de l'écosystème sont à jour côté utilisateur.
- **Un repo utilisateur mal configuré** (permissions, submodules non déclarés) peut produire des comportements inattendus. Chrysalide vérifie le cas standard, pas tous les cas exotiques.

## Recommandations utilisateur

- Ne jamais activer `allow_network=true` sans lire attentivement la whitelist étendue qui sera appliquée.
- Toujours inspecter le diff dans le worktree avant de merger.
- Ne pas donner à Chrysalide accès à des repos qui contiennent des secrets non-`.gitignore`d.
- Faire tourner Chrysalide sur un compte utilisateur non-root.
- En cas de doute, utiliser la Sandbox v2 (Docker) pour une isolation forte.

## Audit et logs

Tous les jobs sont persistés dans SQLite (`~/.chrysalide/jobs.db`) avec :

- Timestamps de début et fin.
- Provider et modèle utilisés.
- Nombre de tokens consommés.
- Statut final et sandbox_path.

Les rapports complets sont conservés tant que la sandbox n'est pas nettoyée. Rétention configurable via `cleanup_after_days`.

## Reporter une vulnérabilité

Non défini pour v0.1. À définir avant toute publication publique (Github security advisory, contact email dédié).
