import os
import time
import logging
from typing import List, Dict, Any, Optional
import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .base import WorkerProvider, ProviderResponse

logger = logging.getLogger(__name__)

class AnthropicProvider(WorkerProvider):
    def __init__(self, model: str):
        self.model = model
        self.client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.InternalServerError))
    )
    async def complete(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: int = 1024,
        temperature: float = 0.2
    ) -> ProviderResponse:
        start_time = time.time()
        
        kwargs = {
            "model": self.model,
            "system": [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        
        if tools:
            kwargs["tools"] = tools
            
        response = await self.client.messages.create(**kwargs)
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        content = ""
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "arguments": block.input
                })
                
        return ProviderResponse(
            content=content,
            tool_calls=tool_calls,
            model=self.model,
            tokens_input=response.usage.input_tokens,
            tokens_output=response.usage.output_tokens,
            latency_ms=latency_ms,
            finish_reason=response.stop_reason or "stop"
        )

    def get_info(self) -> Dict[str, str]:
        return {"name": "anthropic", "model": self.model}