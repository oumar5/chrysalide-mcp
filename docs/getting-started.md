# Getting Started — pour l'implémenteur

Ce document est destiné à l'agent d'implémentation (Antigravity ou humain). Il donne l'ordre de construction recommandé, les décisions déjà prises, et les points d'attention. Il ne contient pas de code — c'est le rôle de l'implémenteur.

## Ordre de build recommandé

Chaque étape doit être fonctionnelle avant de passer à la suivante — pas de code mort en anticipation.

### Étape 1 — Squelette du package

Un package Python 3.11+ installable. Le point d'entrée `python -m chrysalide` doit démarrer proprement (même s'il ne fait rien encore) et sortir sans erreur. Ce squelette valide que le packaging et le layout `src/` fonctionnent avant tout ajout de logique.

Dépendances principales à prévoir : SDK MCP Python, Pydantic, pydantic-settings, aiosqlite, SDKs LLM (OpenAI, Anthropic, Gemini), httpx pour Ollama.

### Étape 2 — Providers

Livrer les 5 providers derrière une interface commune. Voir [providers.md](providers.md) pour l'interface et les modèles recommandés. Tests unitaires avec des réponses HTTP mockées — pas d'appel réel à un LLM en CI.

### Étape 3 — Sandbox

Livrer la classe `Sandbox` basée sur `git worktree`. Le worktree doit se créer, exposer un chemin, refuser toute opération hors de ce chemin, et se nettoyer sur demande. Voir [sandbox.md](sandbox.md). Test unitaire qui crée et supprime un worktree sur un repo git temporaire.

### Étape 4 — Agent tools

Livrer les 4 familles d'outils : `fs`, `shell` (avec whitelist), `git`, `report`. Chaque outil refuse toute action hors sandbox et respecte les limites configurées. Voir [agent-tools.md](agent-tools.md). Tests unitaires sur les cas de refus.

### Étape 5 — Agent loop

Livrer la boucle plan-act-validate-correct avec un provider stubbé (réponses scriptées). Voir [agent-loop.md](agent-loop.md). Le stub permet de valider la boucle sans dépendre d'un LLM réel.

### Étape 6 — Orchestrator & job store

Livrer le gestionnaire de jobs asynchrones avec store SQLite. Les endpoints internes `start_task`, `get_status`, `get_report`, `cancel_task` doivent être fonctionnels (indépendamment de leur exposition MCP). Tests avec plusieurs jobs en parallèle.

### Étape 7 — Serveur MCP

Exposer les 4 tools via le SDK MCP officiel. Voir [mcp-tools.md](mcp-tools.md). Transport stdio prioritaire, HTTP/SSE en bonus. Test manuel avec Claude Code en client.

### Étape 8 — Test end-to-end Calculator

Un test qui tourne avec un vrai LLM (GPT-4o-mini par défaut) et produit un rapport `success` sur la consigne Calculator. Voir [testing.md](testing.md) section "End-to-end".

### Étape 9 — Documentation utilisateur

Compléter le README avec quick start pratique, ajouter des exemples de configuration, un CHANGELOG.

## Décisions déjà prises — ne pas réouvrir

Ces décisions sont arrêtées. L'implémenteur ne doit pas les remettre en question sans raison technique forte :

1. Python 3.11+ (pas 3.10, pas 3.12+ requis).
2. Sandbox = git worktree pour v1. Docker en v0.2.
3. Un seul Agent par job pour v1. Multi-agents en v0.3.
4. Architecture étoile, pas hiérarchique. Pas de mini-architecte.
5. Whitelist de commandes shell. Pas de shell libre, jamais.
6. Provider par défaut : OpenAI GPT-4o-mini. Fallback configurable.
7. Store de jobs = SQLite local dans `~/.chrysalide/jobs.db`.
8. Le rapport est structuré JSON avec version markdown lisible en parallèle.
9. Le Cerveau ne merge jamais automatiquement. Chrysalide ne touche pas au repo utilisateur.

## Points d'attention critiques

- Le rapport optimiste est le failure mode principal. Voir [agent-loop.md](agent-loop.md) section "Anti-optimisme".
- Un test qui ne parse pas doit compter comme un échec, pas comme un succès silencieux.
- Timeouts partout : par commande shell, par itération, par job global.
- Pas de réseau depuis la sandbox par défaut. Option activable par job.
- Les logs de l'Agent doivent être capturés en entier, sinon le debug est impossible.

## Ce qu'il ne faut PAS faire

- Ajouter une UI web. Le produit est un serveur MCP, pas une application.
- Faire du fine-tuning ou du RAG. Les prompts sont statiques + injection de contexte.
- Écrire des tests contre un vrai LLM en CI. Tous les tests unitaires utilisent des mocks. Les tests intégration sont opt-in.
- Chercher à "améliorer" les prompts en cours de route. La structure des prompts est décrite dans [agent-loop.md](agent-loop.md) — les modifier seulement si le end-to-end échoue de façon reproductible.
- Ajouter des dépendances lourdes (LangChain, LangGraph, CrewAI…). Le contrôle vient du code interne, pas d'un framework.

## Livrables finaux

- Package `chrysalide-mcp` installable.
- Commande `python -m chrysalide` qui démarre le serveur MCP en stdio.
- Test end-to-end Calculator qui passe.
- Documentation à jour dans `/docs`.
- `CHANGELOG.md` avec les versions livrées.
