# chrysalide-mcp

> Serveur MCP agentique. Le Cerveau (IDE) dépose une consigne de feature complète, l'Agent transforme dans une sandbox isolée, et un rapport vérifiable en émerge.

## En une phrase

Chrysalide reçoit **une consigne** ("ajoute un système d'auth JWT avec tests"), boucle en interne (plan → act → validate → correct) dans une **sandbox git worktree**, et rend au Cerveau **un rapport structuré** (diff, tests exécutés, décisions, blocages). Le Cerveau n'orchestre pas — il valide.

## Positionnement

- **Pas un remplacement de Claude Code / Cursor.** Ceux-ci gardent le Cerveau dans la boucle en permanence.
- **Pas un agent qui commit.** La sandbox reste isolée du repo utilisateur ; l'intégration est manuelle.
- **Pas un système multi-agents libre.** Architecture **étoile stricte**, superviseur unique.

Objectif principal : **économiser les tokens du Cerveau**. Le Cerveau fait un input (consigne) et lit un output (rapport). Peu importe combien de tokens l'Agent brûle en interne.

## Documentation

Voir `docs/` :

| Document | Contenu |
|---|---|
| [Getting Started](docs/getting-started.md) | Ordre de build recommandé pour l'implémenteur |
| [Architecture](docs/architecture.md) | Composants, flux, diagrammes |
| [MCP Tools](docs/mcp-tools.md) | Spec des 4 tools exposés (schemas) |
| [Agent Loop](docs/agent-loop.md) | Boucle interne, prompts, escalade |
| [Sandbox](docs/sandbox.md) | git worktree v1, Docker v2 |
| [Agent Tools](docs/agent-tools.md) | fs, shell, git, report |
| [Report Schema](docs/report-schema.md) | JSON schema complet |
| [Providers](docs/providers.md) | OpenAI, Anthropic, Gemini, Ollama, Azure |
| [Security](docs/security.md) | Whitelist, limites, réseau off |
| [Configuration](docs/configuration.md) | .env, YAML, budget |
| [Testing](docs/testing.md) | Stratégie de tests |
| [Roadmap](docs/roadmap.md) | v0.1 → v0.4 |
| [Glossary](docs/glossary.md) | Vocabulaire du projet |

## Quick start (utilisateur)

- Cloner le repo, créer un venv Python 3.11+, installer en mode dev.
- Copier `.env.example` vers `.env` et renseigner les clés API (OpenAI, Anthropic, ou autre).
- Lancer le serveur MCP en stdio via `python -m chrysalide`.
- Dans l'IDE (Claude Code, Antigravity, VS Code), ajouter `chrysalide-mcp` comme serveur MCP.

Détails précis dans [docs/getting-started.md](docs/getting-started.md).

## Cas d'usage minimal (test end-to-end)

**Consigne** : "Dans `sample_repo/`, ajoute une classe `Calculator` avec `add`, `subtract`, `multiply`, `divide` (gère la division par zéro), et des tests pytest complets."

**Résultat attendu** :

- Fichiers `calculator.py` et `test_calculator.py` créés dans la sandbox.
- `pytest` sort en exit 0.
- Rapport listant 4 méthodes, 5+ tests, 0 blocage.
- Le repo original est intact — aucun fichier modifié en dehors de la sandbox.

## Licence

MIT
