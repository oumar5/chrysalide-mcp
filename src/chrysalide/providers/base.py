from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from pydantic import BaseModel

class ProviderResponse(BaseModel):
    """Réponse unifiée d'un fournisseur LLM."""
    content: str
    tool_calls: List[Dict[str, Any]] = []  # format: {"id": "...", "name": "...", "arguments": {...}}
    model: str
    tokens_input: int = 0
    tokens_output: int = 0
    latency_ms: int = 0
    finish_reason: str = "stop"

class WorkerProvider(ABC):
    """Interface commune pour tous les fournisseurs LLM."""
    
    @abstractmethod
    async def complete(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: int = 1024,
        temperature: float = 0.2
    ) -> ProviderResponse:
        """
        Génère une complétion à partir d'un prompt système et de messages.
        Les outils sont au format JSON Schema (standard OpenAI).
        """
        pass
        
    @abstractmethod
    def get_info(self) -> Dict[str, str]:
        """Retourne les informations du provider (nom, modèle)."""
        pass
