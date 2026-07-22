# Architecture

## Vue d'ensemble

Chrysalide est un serveur MCP asynchrone qui expose des jobs long-running. Chaque job instancie un Agent autonome dans une sandbox et retourne un rapport structuré.

```text
┌──────────────────────────────────────────────────────────────────┐
│                          CERVEAU (IDE)                            │
│                    Claude Code / Antigravity                      │
│                                                                   │
│  Consigne feature complète                    Rapport vérifiable  │
│         │                                              ▲          │
└─────────┼──────────────────────────────────────────────┼──────────┘
          │ MCP tool call                                │
          ▼                                              │
┌────────────────────────────────────────────────────────┴──────────┐
│                    CHRYSALIDE SERVER (MCP)                        │
│                                                                   │
│  Transport : stdio (v1) + HTTP/SSE (bonus)                        │
│                                                                   │
│  Tools exposés :                                                  │
│   • chrysalide_start_task    fire-and-forget → { job_id }         │
│   • chrysalide_get_status    poll → { status, progress, phase }   │
│   • chrysalide_get_report    lecture rapport final                │
│   • chrysalide_cancel_task   kill un job en cours                 │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │            ORCHESTRATOR (job runner asyncio)                │  │
│  │                                                             │  │
│  │  Store : SQLite (~/.chrysalide/jobs.db)                     │  │
│  │  Un job = une tâche asyncio en tâche de fond                │  │
│  │                                                             │  │
│  │  Cycle :                                                    │  │
│  │   1. Sandbox.create   (git worktree)                        │  │
│  │   2. Agent.run        (goal, sandbox, budget)               │  │
│  │   3. ReportBuilder    (agrège les findings)                 │  │
│  │   4. Persist          (garde la sandbox pour review)        │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                       AGENT (autonome)                      │  │
│  │                                                             │  │
│  │  Modèle : provider configuré (OpenAI/Anthropic/Ollama…)     │  │
│  │                                                             │  │
│  │  Boucle : PLAN → ACT → VALIDATE → CORRECT (max N)           │  │
│  │                                                             │  │
│  │  Outils disponibles :                                       │  │
│  │   • fs.read / fs.write / fs.list  (borné à la sandbox)      │  │
│  │   • shell.exec                    (whitelist)               │  │
│  │   • git.diff / git.status         (dans le worktree)        │  │
│  │   • report.emit_finding / escalate                          │  │
│  └─────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────┘
```

## Composants et responsabilités

### `chrysalide.server`

Rôle : exposer l'API MCP. Aucune logique métier.

- Enregistre les 4 tools, valide les inputs, délègue à l'Orchestrator.
- Contient les modèles Pydantic partagés (JobConfig, JobStatus, ReportPayload).

### `chrysalide.orchestrator`

Rôle : gérer le cycle de vie d'un job.

- Créer les jobs, lancer les tâches asyncio, persister les états.
- Adaptateur SQLite (via aiosqlite) pour le CRUD des jobs et rapports.
- Créer et nettoyer les worktrees git via la classe Sandbox.
- Agréger les findings de l'Agent en rapport final via ReportBuilder.

### `chrysalide.agent`

Rôle : boucle plan-act-validate-correct.

- Classe Agent exposant une méthode `run` qui prend un goal, une sandbox, un budget.
- Une classe par phase (`plan`, `act`, `validate`, `correct`) — factorisable.
- Les outils de l'Agent (`fs`, `shell`, `git`, `report`) — voir [agent-tools.md](agent-tools.md).
- Les prompts sont des fichiers markdown avec placeholders interpolés à l'exécution.

### `chrysalide.providers`

Rôle : abstraire les APIs LLM derrière une interface unique.

- Une classe abstraite `WorkerProvider` avec méthode `complete`.
- Cinq implémentations : OpenAI, Anthropic, Gemini, Ollama, Azure OpenAI.
- Une factory qui instancie le provider selon la config.

### `chrysalide.config`

Rôle : centraliser les paramètres.

- Settings via pydantic-settings, lus depuis `.env`.
- Fichiers YAML pour la whitelist de commandes et les options de sandbox.

## Flux d'exécution

### Cas nominal — success

1. Le Cerveau appelle le tool `chrysalide_start_task` avec goal, repo_path, budget.
2. L'Orchestrator crée un `job_id`, persiste l'état `pending`.
3. Un worktree git est créé sur une branche jetable `chrysalide/<job_id>`.
4. L'Agent est lancé dans une tâche asyncio en tâche de fond. L'état passe à `running`.
5. L'Agent boucle : PLAN décompose, ACT écrit du code via `fs.write`, VALIDATE exécute les commandes via `shell.exec`, CORRECT analyse les échecs et re-tente. Chaque étape émet un finding.
6. Quand toutes les validations passent, la boucle s'arrête.
7. L'Orchestrator agrège les findings en rapport final, le persiste, met l'état à `done`.
8. Le Cerveau poll le statut, appelle `chrysalide_get_report` quand `report_ready=true`.

### Cas d'échec — escalated

Après N itérations sans progrès (mêmes erreurs qui persistent), l'Agent appelle `report.escalate` avec une raison. Le rapport final a `status="escalated"` et contient un blocker explicite. Le Cerveau décide : ré-instruire, clarifier, ou reprendre la main.

### Cas d'annulation

Le Cerveau appelle `chrysalide_cancel_task`. La tâche asyncio est annulée, l'état passe à `cancelled`, la sandbox est **conservée** pour inspection.

## Décisions architecturales clés

### Asyncio plutôt que threads

Le SDK MCP Python est déjà async. Les providers LLM sont IO-bound. Les commandes shell tournent en subprocess async. Les threads n'apporteraient rien et compliqueraient la gestion d'état.

### SQLite plutôt que fichiers JSON

Multi-job en parallèle → besoin de locking → SQLite le gère naturellement. Persistance à travers les redémarrages du serveur. Requêtes utiles (jobs récents, jobs à nettoyer).

### git worktree plutôt que clone

Beaucoup plus rapide (partage le `.git`). Léger sur le disque. Nettoyage propre. Isolation suffisante pour v1.

### Pas de mini-architecte

Empiriquement dégrade la performance dans les systèmes multi-agents. Ajoute des couches de traduction inutiles. Voir [glossary.md](glossary.md) et [agent-loop.md](agent-loop.md).

## Non-goals

- Pas d'UI web. Serveur MCP uniquement.
- Pas de multi-tenant. Un utilisateur = une instance.
- Pas de RAG. L'Agent lit ce qu'on lui donne, ne fait pas de recherche sémantique.
- Pas d'auto-merge. Le Cerveau ou l'utilisateur intègre manuellement.
