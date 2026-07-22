import os
from typing import Optional
from .base import WorkerProvider

def create_provider(spec: str) -> WorkerProvider:
    """
    Factory pour instancier un provider.
    spec: format 'provider:model' (ex: 'openai:gpt-4o-mini')
    """
    if ":" not in spec:
        raise ValueError(f"Spécification de provider invalide: {spec}. Format attendu: 'provider:model'")
        
    provider_name, model = spec.split(":", 1)
    provider_name = provider_name.lower()
    
    if provider_name == "openai":
        from .openai_provider import OpenAIProvider
        return OpenAIProvider(model)
    elif provider_name == "anthropic":
        from .anthropic_provider import AnthropicProvider
        return AnthropicProvider(model)
    elif provider_name == "gemini":
        from .gemini_provider import GeminiProvider
        return GeminiProvider(model)
    elif provider_name == "ollama":
        from .ollama_provider import OllamaProvider
        return OllamaProvider(model)
    elif provider_name == "azure":
        from .azure_provider import AzureProvider
        return AzureProvider(model)
    else:
        raise ValueError(f"Provider inconnu: {provider_name}")

def get_default_provider() -> WorkerProvider:
    """Retourne le provider par défaut configuré via l'environnement."""
    spec = os.getenv("CHRYSALIDE_DEFAULT_PROVIDER", "openai:gpt-4o-mini")
    return create_provider(spec)

def get_fallback_provider() -> Optional[WorkerProvider]:
    """Retourne le provider de secours s'il est configuré."""
    spec = os.getenv("CHRYSALIDE_FALLBACK_PROVIDER")
    if not spec:
        return None
    return create_provider(spec)
