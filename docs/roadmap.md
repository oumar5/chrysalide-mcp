# Roadmap

Progression par versions. Chaque version a des critères d'acceptation clairs — ne pas passer à la suivante avant qu'ils soient tous verts.

## v0.1 — Cœur fonctionnel

**Objectif** : un job Chrysalide peut être lancé depuis un IDE, tourne dans une sandbox git worktree, et produit un rapport structuré exploitable.

**Périmètre** :

- 1 Agent par job (pas de parallélisme).
- Sandbox git worktree uniquement (pas de Docker).
- Provider par défaut : OpenAI GPT-4o-mini. Anthropic et Ollama supportés en option.
- Boucle plan → act → validate → correct fonctionnelle.
- Rapport JSON + version markdown.
- Serveur MCP en transport stdio.
- Pas d'escalade explicite encore (escalade uniquement par budget dépassé ou détection de boucle).

**Critères d'acceptation** :

- Le test e2e "Calculator" passe avec `status = success` avec GPT-4o-mini.
- `pip install -e ".[dev]"` fonctionne sur macOS et Linux, Python 3.11+.
- `python -m chrysalide` démarre le serveur MCP sans erreur.
- Configuré comme MCP server dans Claude Code, les 4 tools sont visibles et appelables.
- Un job annulé conserve bien sa sandbox pour inspection.
- Couverture de tests unit + integration > 80 % sur orchestrator et agent.
- Documentation à jour dans `/docs`.

## v0.2 — Robustesse et escalade

**Objectif** : le système est fiable et négocie ses limites intelligemment.

**Ajouts** :

- Escalade explicite via `report.escalate` avec raisons structurées.
- Sandbox Docker en option (backend configurable dans `sandbox_config.yaml`).
- Support Ollama pleinement testé (au moins Qwen2.5-coder:14b).
- Fallback provider fonctionnel (primary → fallback après retries épuisés).
- Prompt caching Anthropic activé côté provider.
- Cache SQLite optionnel pour les phases PLAN identiques.
- Nettoyage automatique des worktrees anciens (opt-in).

**Critères d'acceptation** :

- Test e2e "escalade contrôlée" : une consigne ambiguë déclenche `status = escalated` avec un blocker clair.
- Sandbox Docker fonctionne end-to-end sur macOS et Linux.
- Un job avec provider primary OpenAI qui échoue bascule automatiquement sur Anthropic.
- La consommation de tokens diminue mesurablement (>30 %) sur un batch de 10 jobs consécutifs grâce au caching.

## v0.3 — Parallélisme intra-job

**Objectif** : accélérer les gros jobs en parallélisant plusieurs Agents sur une même tâche.

**Ajouts** :

- Un job peut instancier N Agents spécialisés en parallèle.
- Rôles suggérés : Creator (écrit le code principal), Tester (écrit les tests), Reviewer (relit et critique avant validation).
- Coordination reste en étoile : chaque Agent parle à l'orchestrator, jamais entre eux directement.
- Un Agent Reviewer peut demander une correction à Creator, mais toujours via l'orchestrator.
- Merge des findings des N agents dans un seul rapport.

**Critères d'acceptation** :

- Test e2e "Calculator + tests écrits par un agent séparé" : deux agents en parallèle produisent le code et les tests, VALIDATE passe.
- Un rapport de job parallélisé identifie clairement quel Agent a fait quoi.

## v0.4 — Qualité et opérabilité

**Objectif** : le système est prêt pour un usage régulier hors expérimentation.

**Ajouts** :

- Métriques et observabilité : dashboard local (page HTML statique) qui lit le store SQLite et affiche les jobs, tokens consommés par jour, taux de succès.
- Transport HTTP/SSE pour utilisation distante.
- Support de rapports négociés en version (le Cerveau demande `report_version: "v1"` ou `"v2"`).
- Support de repos non-git (créer un git init temporaire pour la sandbox).
- Cleanup CLI (`python -m chrysalide cleanup --older-than 30d`).

**Critères d'acceptation** :

- Dashboard local montre au moins jobs récents, tokens consommés, statuts.
- Un client distant peut se connecter via HTTP/SSE et lancer un job.
- CLI cleanup fonctionne et n'efface jamais un job en cours.

## Idées reportées (pas dans la roadmap actuelle)

Ces idées ont été discutées et **rejetées ou reportées** :

- **Mini-architecte intermédiaire.** Rejeté : dégrade la performance empirique dans les systèmes multi-agents.
- **Fine-tuning d'un modèle dédié.** Reporté : pas de valeur claire tant que les modèles généralistes suffisent.
- **UI web complète.** Rejeté : hors périmètre. Le produit est un serveur MCP.
- **Multi-tenant.** Reporté : nécessite un modèle d'authentification et de facturation, pas prioritaire.
- **Auto-merge après validation humaine.** Reporté : risqué, potentiellement en v0.5+ derrière un flag.
- **Support Windows natif.** Reporté : macOS et Linux prioritaires. Windows via WSL en attendant.
