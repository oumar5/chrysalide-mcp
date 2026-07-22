# Sandbox

## Principe

L'Agent **n'écrit jamais** dans le repo utilisateur. Toutes les modifications ont lieu dans une **sandbox isolée**. Deux implémentations sont prévues :

- **v1 — git worktree** : léger, natif, suffisant pour la plupart des cas.
- **v2 — Docker container** : isolation forte, pour tâches sensibles ou multi-tenant.

Cette doc couvre v1 en détail, v2 en design.

## Sandbox v1 — git worktree

### Cycle de vie

**Création** : la classe Sandbox expose une méthode `create` qui prend le chemin du repo, la branche de base, et le job_id. Elle réalise les opérations suivantes :

- Vérifier que le repo est bien un repo git.
- Vérifier que la branche de base existe.
- Ajouter `.chrysalide/` au `.gitignore` du repo si absent.
- Créer un worktree via `git worktree add` dans `.chrysalide/worktrees/<job_id>` sur une branche jetable nommée `chrysalide/<job_id>`.
- Retourner le chemin du worktree.

**Exécution de commandes** : la sandbox expose une méthode `execute` qui prend une commande et un timeout. Elle lance la commande via un subprocess async, avec :

- `cwd` forcé sur le chemin du worktree (jamais ailleurs).
- Un environnement réduit : on part de l'env du processus parent, on retire les clés sensibles (`AWS_*`, `SSH_*`, `GITHUB_TOKEN`, etc), et on ne garde qu'une whitelist explicite (voir `sandbox_config.yaml`).
- Capture de stdout et stderr en pipe.
- Timeout appliqué au processus.

**Conservation après le job** : la sandbox est **conservée** après le job pour permettre au Cerveau d'inspecter le résultat.

**Nettoyage explicite** : la méthode `cleanup` supprime le worktree via `git worktree remove --force` et supprime la branche associée via `git branch -D`. Elle n'est jamais appelée automatiquement à la fin d'un job.

**Nettoyage automatique différé** : un nettoyage périodique optionnel supprime les worktrees `chrysalide/*` plus vieux que N jours (défaut : 7 jours). Voir [configuration.md](configuration.md).

### Intégration côté utilisateur

Après lecture du rapport, l'utilisateur peut :

- Se déplacer dans le worktree pour inspecter le diff avec les commandes git usuelles.
- Merger la branche `chrysalide/<job_id>` dans sa branche principale.
- Ou copier certains fichiers manuellement puis supprimer le worktree et la branche.

Chrysalide ne fait rien de ça automatiquement.

## Contraintes strictes

Toute lecture ou écriture par l'Agent doit être **bornée à la sandbox**. La classe Sandbox expose une méthode utilitaire qui vérifie qu'un chemin résolu est bien à l'intérieur du worktree. Toute tentative de lire ou écrire hors sandbox lève une exception `SandboxViolation`, capturée par l'orchestrator et loggée comme un blocker.

## Cas particuliers

### Submodules et symlinks

- Les submodules git ne sont pas supportés en v1. Si le repo cible contient un submodule, l'orchestrator renvoie une erreur `UNSUPPORTED_SUBMODULE`.
- Les symlinks qui sortent du worktree sont refusés silencieusement — l'Agent voit une erreur `Permission denied`.

### Fichiers volumineux

Limite par défaut : 1 Mo par fichier écrit. Configurable dans `sandbox_config.yaml`. Dépassement → l'outil `fs.write` renvoie une erreur à l'Agent.

### Espace disque total

Limite optionnelle sur la taille totale de la sandbox (désactivée par défaut). Si activée, `fs.write` refuse au-delà.

### Réseau

Par défaut, la sandbox v1 n'isole pas le réseau (c'est une limite de git worktree — il n'y a pas de namespace réseau séparé). Le contrôle du réseau se fait au niveau des commandes shell :

- `pip install`, `npm install`, `curl`, `wget` sont **absents de la whitelist par défaut**.
- Si `allow_network = true` est passé dans le job, ces commandes sont ajoutées à la whitelist locale au job.

Pour une isolation réseau réelle, il faut passer à la Sandbox v2 (Docker).

## Sandbox v2 — Docker (design)

Non implémenté en v0.1. Design de référence :

- La sandbox crée d'abord un worktree comme en v1.
- Puis lance un conteneur Docker avec le worktree monté en volume.
- Le conteneur a le réseau désactivé (`--network=none`).
- Des limites CPU et mémoire sont appliquées.
- Le système de fichiers est en lecture seule sauf le point de montage du worktree.
- Une image runtime standardisée est fournie (Python, Node, Go préinstallés).

Avantages : isolation réseau complète, limites de ressources, runtime standardisé.

Inconvénients : Docker doit être installé, overhead de démarrage, complexité de maintenance d'image.

Décision reportée à la v0.2.

## Configuration

Voir [configuration.md](configuration.md) — la clé `sandbox` expose :

- `backend` : `worktree` ou `docker`.
- `worktree_root` : chemin racine des worktrees créés (défaut `.chrysalide/worktrees`).
- `max_file_size_mb` : taille max par fichier écrit (défaut 1).
- `max_total_size_mb` : taille max totale de la sandbox (désactivée par défaut).
- `cleanup_after_days` : nettoyage automatique des worktrees anciens (défaut 7).
- `env_whitelist` : liste des variables d'environnement à préserver dans la sandbox.

## Tests

Voir [testing.md](testing.md). Tests unitaires critiques :

- Création puis suppression d'un worktree sur un repo temporaire.
- Détection de tentative d'écriture hors sandbox.
- Refus de commandes hors whitelist.
- Respect de la limite de taille de fichier.
- Env sensibles non transmis au subprocess.
