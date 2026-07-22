import pytest
import json
import asyncio
from unittest.mock import AsyncMock, MagicMock
from chrysalide.agent.agent import ChrysalideAgent
from chrysalide.models import JobConfig, Budget, JobStatus
from chrysalide.providers.base import ProviderResponse
from chrysalide.providers.base import WorkerProvider

class MockProvider(WorkerProvider):
    def __init__(self, responses):
        self.responses = responses
        self.call_count = 0
        
    async def complete(self, system_prompt, messages, tools=None, **kwargs):
        resp = self.responses[self.call_count]
        self.call_count += 1
        return resp
        
    def get_info(self):
        return {"name": "mock", "model": "mock-model"}

@pytest.fixture
def mock_sandbox():
    sandbox = AsyncMock()
    sandbox.worktree_path = "/tmp/fake"
    return sandbox

@pytest.fixture
def mock_store():
    store = AsyncMock()
    return store

@pytest.mark.asyncio
async def test_agent_loop_success_first_try(mock_sandbox, mock_store):
    # Setup mock responses
    responses = [
        # PLAN phase response
        ProviderResponse(
            content="",
            model="mock",
            tool_calls=[{
                "name": "submit_plan",
                "arguments": json.dumps({
                    "subtasks": [{"title": "t1", "files": ["f1"]}],
                    "validation_commands": ["test cmd"],
                    "risks": []
                })
            }]
        ),
        # ACT phase response (uses fs.write, then next call is empty tool calls to finish)
        ProviderResponse(
            content="J'ai ecrit le fichier",
            model="mock",
            tool_calls=[{"name": "fs.write", "arguments": {"path": "f1", "content": "hello"}}]
        ),
        ProviderResponse(
            content="TERMINE",
            model="mock",
            tool_calls=[]
        )
    ]
    provider = MockProvider(responses)
    
    # Mock validation command success
    mock_sandbox.execute.return_value = (0, b"Success output", b"")
    
    agent = ChrysalideAgent(
        provider=provider,
        sandbox=mock_sandbox,
        job_id="test_job_1",
        store=mock_store,
        budget=Budget()
    )
    
    report = await agent.run("Goal test")
    
    assert report.status == JobStatus.DONE
    assert report.diff_summary.files == 1
    assert len(report.commands_executed) == 1
    assert report.commands_executed[0].cmd == "test cmd"
    assert report.commands_executed[0].exit_code == 0
    assert "test cmd" in report.commands_executed[0].cmd

@pytest.mark.asyncio
async def test_agent_loop_correct_phase(mock_sandbox, mock_store):
    # Setup mock responses
    responses = [
        # PLAN
        ProviderResponse(
            content="", model="mock",
            tool_calls=[{
                "name": "submit_plan",
                "arguments": json.dumps({
                    "subtasks": [{"title": "t1", "files": ["f1"]}],
                    "validation_commands": ["test cmd"],
                    "risks": []
                })
            }]
        ),
        # ACT 1
        ProviderResponse(content="Je code", model="mock", tool_calls=[{"name": "fs.write", "arguments": {"path": "f1", "content": "bug"}}]),
        ProviderResponse(content="TERMINE", model="mock", tool_calls=[]),
        # CORRECT
        ProviderResponse(content="Ah je vois l'erreur", model="mock", tool_calls=[]),
        # ACT 2
        ProviderResponse(content="Je corrige", model="mock", tool_calls=[{"name": "fs.write", "arguments": {"path": "f1", "content": "fix"}}]),
        ProviderResponse(content="TERMINE", model="mock", tool_calls=[]),
    ]
    provider = MockProvider(responses)
    
    # Mock sandbox to fail first, then succeed
    mock_sandbox.execute.side_effect = [
        (1, b"Failed", b"Error"),
        (0, b"Success", b"")
    ]
    
    agent = ChrysalideAgent(
        provider=provider,
        sandbox=mock_sandbox,
        job_id="test_job_2",
        store=mock_store,
        budget=Budget()
    )
    
    report = await agent.run("Goal test")
    
    assert report.status == JobStatus.DONE
    assert len(report.commands_executed) == 2
    assert report.commands_executed[0].exit_code == 1
    assert report.commands_executed[1].exit_code == 0
