# Testing

## Stratégie

Trois niveaux de tests :

1. **Unit** — testent une classe ou fonction en isolation avec des mocks. Rapides, tournent en CI sur chaque commit.
2. **Integration** — testent l'intégration de plusieurs composants (Sandbox + Agent + provider stubbé). Sans appel réseau réel. Tournent en CI.
3. **End-to-end** — testent le système complet avec un vrai LLM. Skip par défaut en CI, activés manuellement (`pytest -m e2e`).

## Framework

- `pytest` comme test runner.
- `pytest-asyncio` pour les tests async.
- `pytest-mock` pour les mocks.
- Marqueurs personnalisés : `unit`, `integration`, `e2e`.

## Tests unit — inventaire minimum

### Providers

Pour chaque provider (OpenAI, Anthropic, Gemini, Ollama, Azure) :

- Réponse success bien parsée.
- Réponse avec tool_calls bien parsée.
- Gestion des erreurs 429 (rate limit) avec retry.
- Gestion des erreurs 401 (auth) sans retry.
- Timeout géré proprement.
- Comptage de tokens correct.

Toutes les requêtes HTTP sont mockées via `pytest-mock` ou `httpx.MockTransport`.

### Sandbox

- Création d'un worktree sur un repo git temporaire.
- Suppression propre du worktree et de la branche.
- Détection de tentative d'écriture hors sandbox.
- Refus de commandes hors whitelist.
- Respect de la limite de taille de fichier.
- Env sensibles non transmis au subprocess.
- Timeout par commande respecté.

### Agent tools

- `fs.read` refuse un chemin hors sandbox.
- `fs.write` refuse un chemin hors sandbox et un fichier trop gros.
- `fs.list` retourne le contenu attendu et refuse hors sandbox.
- `shell.exec` refuse une commande hors whitelist.
- `report.emit_finding` accumule correctement dans l'état.
- `report.escalate` termine la boucle et crée un blocker.

### Agent loop (avec provider stubbé)

- Success au premier essai (VALIDATE passe direct).
- Échec puis correction réussie à l'itération 2.
- Escalade explicite via `report.escalate`.
- Escalade par détection de boucle (mêmes erreurs 3 fois).
- Escalade par dépassement de `max_iterations`.
- Escalade par dépassement de `max_tokens_total`.
- Anti-optimisme : rejet d'un finding qui déclare success sans que VALIDATE ne passe.

### Orchestrator

- Création d'un job persisté en SQLite.
- Update de status pendant l'exécution.
- Récupération d'un job par `job_id`.
- Gestion de plusieurs jobs en parallèle sans corruption d'état.
- Annulation d'un job en cours (asyncio.Task cancelled proprement).

### Serveur MCP

- Chaque tool renvoie le bon schéma d'output.
- Erreurs mappées correctement (`JOB_NOT_FOUND`, `REPORT_NOT_READY`, etc).
- Validation Pydantic des inputs rejette les payloads malformés.

## Tests integration — inventaire minimum

Ces tests utilisent un provider stubbé (réponses scriptées en JSON) mais font tourner la boucle complète et la sandbox réelle.

- Scénario "Calculator" avec un stub qui produit le bon code au premier essai.
- Scénario "test qui échoue" avec un stub qui écrit du code cassé à l'itération 1, corrige à l'itération 2.
- Scénario "escalade" avec un stub qui écrit du code cassé identique 3 fois → l'orchestrator détecte la boucle et escalade.
- Scénario "annulation" : un job long est lancé, annulé après 2 itérations, la sandbox est bien conservée.

## Tests end-to-end

Un seul test e2e obligatoire pour la v0.1 :

**Scénario Calculator**

- Setup : un dossier temporaire initialisé comme repo git vide.
- Consigne : "Dans ce repo, crée `calculator.py` avec une classe `Calculator` exposant `add`, `subtract`, `multiply`, `divide` (gère la division par zéro). Crée aussi `test_calculator.py` avec des tests pytest complets. `validation_commands` : `python -m py_compile calculator.py`, `pytest test_calculator.py -v`."
- Exécution : lance un job Chrysalide avec le provider par défaut (GPT-4o-mini).
- Attentes :
  - Le job termine avec `status = "success"` en moins de 15 itérations.
  - `calculator.py` et `test_calculator.py` existent dans la sandbox.
  - `pytest` retourne exit 0.
  - Le rapport contient au moins 5 findings de type `command_run` et au moins 2 de type `file_write`.
  - Aucun fichier modifié en dehors de la sandbox (assertion sur `git status` du repo racine).
- Skip par défaut en CI, activation manuelle via un marker `e2e` ou une variable d'env `RUN_E2E=1`.

## Fixtures partagées

Fixtures principales à fournir dans `conftest.py` :

- `tmp_git_repo` : crée un repo git temporaire vide, retourne son chemin, nettoie après le test.
- `stub_provider` : fournit un `WorkerProvider` avec réponses scriptables. Interface : `stub.script([...réponses])`.
- `sandbox_factory` : crée une Sandbox liée à un `tmp_git_repo`, nettoie après le test.
- `agent_factory` : crée un Agent avec un `stub_provider` et une `sandbox` prêts.

## CI

- Sur chaque commit : `pytest -m "unit or integration"`.
- Sur main (post-merge) : ajouter `-m e2e` optionnel via workflow avec secret pour la clé API.
- Coverage minimum : 80 % sur `chrysalide/orchestrator/` et `chrysalide/agent/` (les zones critiques). Providers et serveur MCP peuvent être moins couverts.

## Tests contre les regressions du LLM

Les LLMs évoluent. Un test e2e qui passait hier peut échouer aujourd'hui. Recommandations :

- Ne pas paniquer si un test e2e devient flaky : investiguer, versionner le modèle utilisé si besoin.
- Garder plusieurs "consignes de référence" pour éviter que le succès dépende d'un seul prompt.
- Considérer un test e2e comme un smoke test, pas une garantie exhaustive.
