import os
import time
import json
import logging
from typing import List, Dict, Any, Optional
import pytest
import openai
from unittest.mock import AsyncMock, patch, MagicMock
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from chrysalide.providers.openai_provider import OpenAIProvider, ProviderResponse

logger = logging.getLogger(__name__)

@pytest.fixture
def mock_openai_client():
    with patch("openai.AsyncOpenAI") as mock_client:
        yield mock_client

@pytest.fixture
def openai_provider(mock_openai_client):
    import os
    os.environ["OPENAI_API_KEY"] = "fake"
    provider = OpenAIProvider(model="text-davinci-003")
    # Désactiver les retries pour les tests pour éviter d'attendre
    async def mock_sleep(x): pass
    provider.complete.retry.sleep = mock_sleep
    return provider

@pytest.fixture
def mock_response():
    response = AsyncMock()
    response.choices = [AsyncMock()]
    response.choices[0].message.content = "Test response"
    response.choices[0].message.tool_calls = []
    response.usage.prompt_tokens = 10
    response.usage.completion_tokens = 20
    response.choices[0].finish_reason = "stop"
    return response

class TestOpenAIProviderHappyPath:
    @pytest.mark.asyncio
    async def test_complete_nominal_case(self, openai_provider, mock_openai_client, mock_response):
        mock_openai_client.return_value.chat.completions.create = AsyncMock(return_value=mock_response)
        system_prompt = "You are a helpful assistant."
        messages = [{"role": "user", "content": "Hello!"}]
        
        response = await openai_provider.complete(system_prompt, messages)
        
        assert response.content == "Test response"
        assert response.tool_calls == []
        assert response.model == "text-davinci-003"
        assert response.tokens_input == 10
        assert response.tokens_output == 20
        assert response.finish_reason == "stop"

    def test_get_info(self, openai_provider):
        info = openai_provider.get_info()
        assert info == {"name": "openai", "model": "text-davinci-003"}

class TestOpenAIProviderEdgeCases:
    @pytest.mark.asyncio
    async def test_complete_empty_messages(self, openai_provider, mock_openai_client, mock_response):
        mock_openai_client.return_value.chat.completions.create = AsyncMock(return_value=mock_response)
        system_prompt = "You are a helpful assistant."
        messages = []
        
        response = await openai_provider.complete(system_prompt, messages)
        
        assert response.content == "Test response"
        assert response.tool_calls == []
        assert response.model == "text-davinci-003"
        assert response.tokens_input == 10
        assert response.tokens_output == 20
        assert response.finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_complete_large_max_tokens(self, openai_provider, mock_openai_client, mock_response):
        mock_openai_client.return_value.chat.completions.create = AsyncMock(return_value=mock_response)
        system_prompt = "You are a helpful assistant."
        messages = [{"role": "user", "content": "Hello!"}]
        
        response = await openai_provider.complete(system_prompt, messages, max_tokens=10000)
        
        assert response.content == "Test response"
        assert response.tool_calls == []
        assert response.model == "text-davinci-003"
        assert response.tokens_input == 10
        assert response.tokens_output == 20
        assert response.finish_reason == "stop"

class TestOpenAIProviderErrorHandling:
    @pytest.mark.asyncio
    async def test_complete_api_rate_limit_error(self, openai_provider, mock_openai_client):
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_openai_client.return_value.chat.completions.create.side_effect = openai.RateLimitError(
            "rate limit", response=mock_response, body=None
        )
        
        system_prompt = "You are a helpful assistant."
        messages = [{"role": "user", "content": "Hello!"}]
        
        with pytest.raises(openai.RateLimitError):
            await openai_provider.complete(system_prompt, messages)

    @pytest.mark.asyncio
    async def test_complete_api_connection_error(self, openai_provider, mock_openai_client):
        mock_request = MagicMock()
        mock_openai_client.return_value.chat.completions.create.side_effect = openai.APIConnectionError(
            request=mock_request
        )
        
        system_prompt = "You are a helpful assistant."
        messages = [{"role": "user", "content": "Hello!"}]
        
        with pytest.raises(openai.APIConnectionError):
            await openai_provider.complete(system_prompt, messages)

    @pytest.mark.asyncio
    async def test_complete_internal_server_error(self, openai_provider, mock_openai_client):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_openai_client.return_value.chat.completions.create.side_effect = openai.InternalServerError(
            "internal error", response=mock_response, body=None
        )
        
        system_prompt = "You are a helpful assistant."
        messages = [{"role": "user", "content": "Hello!"}]
        
        with pytest.raises(openai.InternalServerError):
            await openai_provider.complete(system_prompt, messages)