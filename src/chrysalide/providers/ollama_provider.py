import os
import time
import json
import logging
from typing import List, Dict, Any, Optional
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .base import WorkerProvider, ProviderResponse

logger = logging.getLogger(__name__)

class OllamaProvider(WorkerProvider):
    def __init__(self, model: str):
        self.model = model
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError))
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
        api_messages.extend(messages)
        
        payload = {
            "model": self.model,
            "messages": api_messages,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            },
            "stream": False
        }
        
        if tools:
            ollama_tools = [{"type": "function", "function": t} for t in tools]
            payload["tools"] = ollama_tools
            
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
            
        latency_ms = int((time.time() - start_time) * 1000)
        
        msg = data.get("message", {})
        content = msg.get("content", "")
        
        tool_calls = []
        if "tool_calls" in msg:
            for idx, tc in enumerate(msg["tool_calls"]):
                fn = tc.get("function", {})
                tool_calls.append({
                    "id": f"call_{idx}",
                    "name": fn.get("name", ""),
                    "arguments": fn.get("arguments", {})
                })
                
        return ProviderResponse(
            content=content,
            tool_calls=tool_calls,
            model=self.model,
            tokens_input=data.get("prompt_eval_count", 0),
            tokens_output=data.get("eval_count", 0),
            latency_ms=latency_ms,
            finish_reason=data.get("done_reason", "stop")
        )

    def get_info(self) -> Dict[str, str]:
        return {"name": "ollama", "model": self.model}
