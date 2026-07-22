# Providers

Abstraction des APIs LLM derrière une interface unique.

## Interface commune

Une classe abstraite `WorkerProvider` est définie avec une méthode `complete` async. Elle accepte :

- Un prompt système (string).
- Une liste de messages (au format role/content, adapté depuis OpenAI-like).
- Une liste de tools (optionnelle) au format JSON Schema.
- Un `max_tokens` de sortie.
- Une `temperature` (défaut bas, autour de 0.2).

Elle retourne un objet `ProviderResponse` contenant :

- Le contenu texte de la réponse.
- Les tool calls éventuels (liste unifiée : id, nom, arguments).
- Le modèle utilisé.
- Les tokens input et output consommés.
- La latence en millisecondes.
- Un `finish_reason` (stop, tool_use, length, error).

Chaque provider concret implémente cette interface. Une méthode `get_info` renvoie le nom du provider et le modèle courant, pour reporting.

## Providers supportés v1

### OpenAI / Azure OpenAI

**Modèles recommandés** :

- Général : `gpt-4o-mini` (par défaut), `gpt-4o`.
- Reasoning : `o4-mini` si disponible.

**Authentification** : variable d'environnement `OPENAI_API_KEY`. Pour Azure : `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT`.

**Tool use** : natif via le paramètre `tools`.

**Notes** :

- Le format JSON strict peut être forcé pour la phase PLAN où on veut un plan JSON parsable.
- Streaming non requis en v1 — l'Agent attend la réponse complète.

### Anthropic

**Modèles recommandés** :

- Général : `claude-haiku-4-5-20251001` (le plus économique).
- Qualité : `claude-sonnet-4-6`.

**Authentification** : `ANTHROPIC_API_KEY`.

**Tool use** : natif via `tools` avec `input_schema` en JSON Schema.

**Prompt caching** : à activer sur le prompt système qui est identique entre itérations d'un même job. Économie substantielle sur les jobs longs.

### Google Gemini

**Modèles recommandés** :

- `gemini-2.0-flash` (par défaut).
- `gemini-2.0-pro` pour tâches complexes.

**Authentification** : `GEMINI_API_KEY`.

**Tool use** : natif via `function_declarations`.

### Ollama (local)

**Modèles recommandés** :

- `qwen2.5-coder:14b` : bon compromis, nécessite ~24 Go de VRAM.
- `qwen2.5-coder:7b` : viable sur Mac M-series ou 8-16 Go VRAM.
- `llama3.1:8b` en fallback généraliste.

**Endpoint** : par défaut `http://localhost:11434/api/chat`.

**Tool use** : supporté sur les modèles récents (Qwen2.5-coder, Llama 3.1+). Le format Ollama est spécifique — l'adaptateur convertit depuis le format JSON Schema unifié.

**Notes** :

- Timeout plus long (30 à 120 secondes selon modèle et matériel).
- Vérifier la disponibilité au démarrage du serveur en interrogeant l'endpoint des tags.

## Factory et sélection

Une factory prend une spec sous forme `<provider>:<model>` et retourne l'instance concrète. Exemples de specs :

- `openai:gpt-4o-mini`
- `anthropic:claude-haiku-4-5-20251001`
- `gemini:gemini-2.0-flash`
- `ollama:qwen2.5-coder:14b`
- `azure:my-deployment-name`

**Provider par défaut** : lu depuis la config (`settings.default_provider`), défaut `openai:gpt-4o-mini`.

**Override par job** : possible via le champ `provider_override` dans l'appel `chrysalide_start_task`.

## Retry et fallback

Chaque appel provider passe par un wrapper de retry :

- Retry sur : timeout réseau, erreur 429 (rate limit), erreurs 5xx.
- **Pas** de retry sur : erreur 400 (bad request), erreur 401 (auth).
- Backoff exponentiel (défaut : 2 secondes de base, jusqu'à 3 tentatives).

**Fallback provider** (optionnel, configurable) :

- Un provider primary et un provider fallback sont déclarés en config.
- Le fallback est activé après épuisement des retries sur le primary.
- Un finding de type `provider_fallback` est émis dans le rapport pour traçabilité.

## Cache

**v1** : pas de cache applicatif. Chaque appel LLM est frais.

**v0.2** : cache optionnel des réponses PLAN identiques (même goal + mêmes contraintes). Store SQLite.

**Prompt caching provider-side** (Anthropic) : activé sur le prompt système partagé — géré au niveau du provider Anthropic, transparent pour le reste.

## Comptage de tokens

Chaque provider retourne `tokens_input` et `tokens_output`. L'orchestrator accumule dans `job.tokens_used` et **stoppe le job** si `budget.max_tokens_total` est atteint.

Fallback si le provider ne retourne pas de count : estimation via un tokenizer approprié (`tiktoken` pour OpenAI, `anthropic-tokenizer` pour Claude). Précision suffisante pour un stop budgétaire — pas de garantie exacte, mais assez proche pour être utile.

## Erreurs typiques

| Erreur | Cause | Traitement |
|---|---|---|
| `AuthenticationError` | Clé API manquante ou invalide | Fail-fast, pas de retry |
| `RateLimitError` | Rate limit dépassé | Retry avec backoff |
| `TimeoutError` | Réseau lent, modèle local surchargé | Retry N fois puis fallback |
| `InvalidToolCallError` | LLM produit un tool call malformé | Message correctif au LLM (max 2 fois) puis escalate |
| `ContentPolicyError` | Refus explicite du provider | Escalate immédiatement |

## Tests

Chaque provider a un fichier de test avec :

- Mocks HTTP couvrant les cas success, rate limit, auth error, timeout.
- Un test d'intégration marqué `integration` (skip en CI par défaut) qui appelle réellement l'API — utile pour valider un changement d'adaptateur, pas pour CI régulière.

Voir [testing.md](testing.md).
