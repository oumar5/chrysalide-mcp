import os
import time
import json
import logging
from typing import List, Dict, Any, Optional
import openai
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .base import WorkerProvider, ProviderResponse

logger = logging.getLogger(__name__)

class OpenAIProvider(WorkerProvider):
    def __init__(self, model: str):
        self.model = model
        self.client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((openai.RateLimitError, openai.APIConnectionError, openai.InternalServerError))
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
        
        api_messages = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            api_messages.append(msg)
            
        kwargs = {
            "model": self.model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        
        if tools:
            openai_tools = [{"type": "function", "function": t} for t in tools]
            kwargs["tools"] = openai_tools
            
        response = await self.client.chat.completions.create(**kwargs)
        
        latency_ms = int((time.time() - start_time) * 1000)
        choice = response.choices[0]
        
        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments)
                })
                
        return ProviderResponse(
            content=choice.message.content or "",
            tool_calls=tool_calls,
            model=self.model,
            tokens_input=response.usage.prompt_tokens if response.usage else 0,
            tokens_output=response.usage.completion_tokens if response.usage else 0,
            latency_ms=latency_ms,
            finish_reason=choice.finish_reason
        )

    def get_info(self) -> Dict[str, str]:
        return {"name": "openai", "model": self.model}