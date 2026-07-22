"""Provider for Azure API Management gateways fronting OpenAI deployments.

This targets URLs like https://<apim>.azure-api.net/<path>/deployments/<model>/chat/completions,
where the gateway expects:
  - `Ocp-Apim-Subscription-Key` header (not Bearer)
  - `api-version` query parameter
The URL layout differs from AsyncAzureOpenAI's assumptions, so we forge base_url
with AsyncOpenAI directly and inject the header via default_headers.
"""

import os
import time
import json
import logging
from typing import List, Dict, Any, Optional

import openai
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .base import WorkerProvider, ProviderResponse

logger = logging.getLogger(__name__)


def _normalize_tools(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Accept both bare {name, parameters} and OpenAI-shaped {type, function}."""
    out: List[Dict[str, Any]] = []
    for t in tools:
        if t.get("type") == "function" and "function" in t:
            out.append(t)
        else:
            out.append({"type": "function", "function": t})
    return out


class AzureAPIMProvider(WorkerProvider):
    """Compatible with Azure APIM gateways that proxy OpenAI deployments."""

    def __init__(self, model: str):
        self.model = model
        endpoint = os.getenv("AZURE_APIM_ENDPOINT") or os.getenv("WORKER_API_BASE_URL")
        api_key = os.getenv("AZURE_APIM_API_KEY") or os.getenv("WORKER_API_KEY")
        api_version = os.getenv("AZURE_APIM_API_VERSION") or os.getenv("WORKER_API_VERSION", "2024-06-01")

        if not endpoint or not api_key:
            raise ValueError(
                "AzureAPIMProvider requires AZURE_APIM_ENDPOINT/API_KEY "
                "(or WORKER_API_BASE_URL/WORKER_API_KEY as fallback)."
            )

        base_url = f"{endpoint.rstrip('/')}/deployments/{self.model}"
        self.client = openai.AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            default_headers={"Ocp-Apim-Subscription-Key": api_key},
            default_query={"api-version": api_version},
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
        retry=retry_if_exception_type(
            (openai.RateLimitError, openai.APIConnectionError, openai.InternalServerError)
        ),
    )
    async def complete(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> ProviderResponse:
        start_time = time.time()

        api_messages = [{"role": "system", "content": system_prompt}]
        api_messages.extend(messages)

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = _normalize_tools(tools)

        response = await self.client.chat.completions.create(**kwargs)

        latency_ms = int((time.time() - start_time) * 1000)
        choice = response.choices[0]

        tool_calls: List[Dict[str, Any]] = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                except json.JSONDecodeError:
                    args = {"_raw": tc.function.arguments}
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": args,
                })

        return ProviderResponse(
            content=choice.message.content or "",
            tool_calls=tool_calls,
            model=self.model,
            tokens_input=response.usage.prompt_tokens if response.usage else 0,
            tokens_output=response.usage.completion_tokens if response.usage else 0,
            latency_ms=latency_ms,
            finish_reason=choice.finish_reason or "stop",
        )

    def get_info(self) -> Dict[str, str]:
        return {"name": "azure_apim", "model": self.model}
