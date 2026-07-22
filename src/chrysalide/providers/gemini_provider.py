import os
import time
import logging
from typing import List, Dict, Any, Optional
from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from google.api_core.exceptions import RetryError, InternalServerError, TooManyRequests

from .base import WorkerProvider, ProviderResponse

logger = logging.getLogger(__name__)

class GeminiProvider(WorkerProvider):
    def __init__(self, model: str):
        self.model = model
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
        retry=retry_if_exception_type((RetryError, InternalServerError, TooManyRequests))
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
        
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part.from_text(msg["content"])]))
            
        config_kwargs = {
            "system_instruction": system_prompt,
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        
        if tools:
            declarations = []
            for t in tools:
                declarations.append({
                    "name": t.get("name"),
                    "description": t.get("description", ""),
                    "parameters": t.get("parameters", {})
                })
            config_kwargs["tools"] = [{"function_declarations": declarations}]
            
        config = types.GenerateContentConfig(**config_kwargs)
        
        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=contents,
            config=config
        )
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        content = ""
        tool_calls = []
        if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.text:
                    content += part.text
                if part.function_call:
                    args = {k: v for k, v in part.function_call.args.items()} if part.function_call.args else {}
                    tool_calls.append({
                        "id": "call_" + part.function_call.name,
                        "name": part.function_call.name,
                        "arguments": args
                    })
                    
        return ProviderResponse(
            content=content.strip(),
            tool_calls=tool_calls,
            model=self.model,
            tokens_input=response.usage_metadata.prompt_token_count if response.usage_metadata else 0,
            tokens_output=response.usage_metadata.candidates_token_count if response.usage_metadata else 0,
            latency_ms=latency_ms,
            finish_reason="stop"
        )

    def get_info(self) -> Dict[str, str]:
        return {"name": "gemini", "model": self.model}
