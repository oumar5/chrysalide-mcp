import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from chrysalide.agent.agent import ChrysalideAgent
from chrysalide.models import Budget, JobStatus
from chrysalide.providers.base import ProviderResponse, WorkerProvider


class ScriptedProvider(WorkerProvider):
    """A minimal provider that returns pre-canned responses in order."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0

    async def complete(self, system_prompt, messages, tools=None, **kwargs):
        if self.call_count >= len(self.responses):
            # Exhausted: return a final message with no tool calls to break loops.
            return ProviderResponse(content="END", model="mock")
        resp = self.responses[self.call_count]
        self.call_count += 1
        return resp

    def get_info(self):
        return {"name": "mock", "model": "mock-model"}


def _plan_response(commands, files=None):
    return ProviderResponse(
        content="",
        model="mock",
        tool_calls=[{
            "name": "submit_plan",
            "arguments": json.dumps({
                "subtasks": [{"title": "t1", "files": files or ["f1.py"]}],
                "validation_commands": commands,
                "risks": [],
            }),
        }],
    )


def _write_response(path, content):
    return ProviderResponse(
        content="Writing",
        model="mock",
        tool_calls=[{"name": "write_file", "arguments": {"path": path, "content": content}}],
    )


def _empty_response(text="TERMINE"):
    return ProviderResponse(content=text, model="mock", tool_calls=[])


@pytest.fixture
def sandbox_with_tmp(tmp_path):
    """A mock sandbox whose get_path() returns a real temp dir — needed for hash/lines tracking.

    Uses MagicMock so sync methods (get_path, worktree_path) stay sync; execute is
    explicitly an AsyncMock to remain awaitable.
    """
    sb = MagicMock()
    sb.get_path.return_value = tmp_path
    sb.worktree_path = tmp_path
    sb.execute = AsyncMock()
    return sb


@pytest.fixture
def mock_store():
    store = AsyncMock()
    return store


@pytest.mark.asyncio
async def test_agent_success_first_try(sandbox_with_tmp, mock_store):
    """Happy path: PLAN → ACT (write real file) → VALIDATE passes → DONE."""
    provider = ScriptedProvider([
        _plan_response(["pytest test.py"]),
        _write_response("f1.py", "def foo():\n    return 42\n"),
        _empty_response(),
    ])
    sandbox_with_tmp.execute.return_value = (0, b"OK", b"")

    agent = ChrysalideAgent(
        provider=provider,
        sandbox=sandbox_with_tmp,
        job_id="test_ok",
        store=mock_store,
        budget=Budget(),
    )
    report = await agent.run("Goal test")

    assert report.status == JobStatus.DONE
    assert report.diff_summary.files == 1
    assert report.files_changed[0].path == "f1.py"
    assert report.files_changed[0].action == "created"
    assert report.files_changed[0].hash.startswith("sha256:")
    assert report.files_changed[0].hash != "sha256:" + "0" * 64
    assert report.files_changed[0].lines == 2
    assert report.files_changed[0].size_bytes > 0
    assert report.diff_summary.added == 2
    assert len(report.commands_executed) == 1
    assert report.commands_executed[0].exit_code == 0
    assert report.integration_hint == "git merge chrysalide/test_ok"


@pytest.mark.asyncio
async def test_agent_correct_then_success(sandbox_with_tmp, mock_store):
    """VALIDATE fails once, CORRECT + ACT retry, VALIDATE passes on 2nd try."""
    provider = ScriptedProvider([
        _plan_response(["pytest test.py"]),
        _write_response("f1.py", "def foo():\n    return 1\n"),
        _empty_response(),
        # CORRECT phase: LLM analyzes, no tool calls
        _empty_response("Ah je vois"),
        # ACT again
        _write_response("f1.py", "def foo():\n    return 42\n"),
        _empty_response(),
    ])
    # First validation fails, second succeeds
    sandbox_with_tmp.execute.side_effect = [
        (1, b"FAIL", b"AssertionError"),
        (0, b"OK", b""),
    ]

    agent = ChrysalideAgent(
        provider=provider,
        sandbox=sandbox_with_tmp,
        job_id="test_correct",
        store=mock_store,
        budget=Budget(),
    )
    report = await agent.run("Goal test")

    assert report.status == JobStatus.DONE
    assert len(report.commands_executed) == 2
    assert report.commands_executed[0].exit_code == 1
    assert report.commands_executed[1].exit_code == 0
    # File should be reported as created (baseline was None), modified content
    assert report.files_changed[0].action == "created"


@pytest.mark.asyncio
async def test_agent_escalates_on_repeated_error_loop(sandbox_with_tmp, mock_store):
    """Same error 3 times in a row → escalation."""
    # Enough responses to cover 3 error cycles
    responses = [_plan_response(["pytest test.py"])]
    for _ in range(3):
        responses.append(_write_response("f1.py", "def foo():\n    return 1\n"))
        responses.append(_empty_response())      # end ACT
        responses.append(_empty_response("Analysing"))  # CORRECT
    provider = ScriptedProvider(responses)
    # Always fail with identical error → same signature every round
    sandbox_with_tmp.execute.return_value = (1, b"same fail", b"same error")

    agent = ChrysalideAgent(
        provider=provider,
        sandbox=sandbox_with_tmp,
        job_id="test_loop",
        store=mock_store,
        budget=Budget(max_iterations=50),
        loop_detection_threshold=3,
    )
    report = await agent.run("Goal test")

    assert report.status == JobStatus.ESCALATED
    assert any(b.description == "Boucle d'erreur détectée" for b in report.blockers)
    assert report.integration_hint is None


@pytest.mark.asyncio
async def test_agent_escalates_on_max_iterations(sandbox_with_tmp, mock_store):
    """Budget max_iterations reached → escalate."""
    provider = ScriptedProvider([_plan_response(["pytest test.py"])])
    sandbox_with_tmp.execute.return_value = (0, b"OK", b"")

    agent = ChrysalideAgent(
        provider=provider,
        sandbox=sandbox_with_tmp,
        job_id="test_maxiter",
        store=mock_store,
        budget=Budget(max_iterations=1),
    )
    # The plan call consumes iteration 1; the loop should then escalate on the next budget check.
    report = await agent.run("Goal test")

    assert report.status == JobStatus.ESCALATED
    assert any("max_iterations" in b.description for b in report.blockers)


@pytest.mark.asyncio
async def test_agent_rejects_stub_code(sandbox_with_tmp, mock_store):
    """Anti-optimism: pass / NotImplementedError / TODO in written .py should escalate."""
    provider = ScriptedProvider([
        _plan_response(["pytest test.py"]),
        _write_response("stub.py", "def foo():\n    pass\n"),
        _empty_response(),
    ])
    sandbox_with_tmp.execute.return_value = (0, b"OK", b"")

    agent = ChrysalideAgent(
        provider=provider,
        sandbox=sandbox_with_tmp,
        job_id="test_stub",
        store=mock_store,
        budget=Budget(),
    )
    report = await agent.run("Goal test")

    assert report.status == JobStatus.ESCALATED
    assert any("Anti-optimism" in b.description for b in report.blockers)


@pytest.mark.asyncio
async def test_agent_escalates_when_no_plan(sandbox_with_tmp, mock_store):
    """PLAN phase without submit_plan tool call → escalate."""
    provider = ScriptedProvider([
        ProviderResponse(content="I don't know what to do", model="mock", tool_calls=[]),
    ])
    sandbox_with_tmp.execute.return_value = (0, b"", b"")

    agent = ChrysalideAgent(
        provider=provider,
        sandbox=sandbox_with_tmp,
        job_id="test_noplan",
        store=mock_store,
        budget=Budget(),
    )
    report = await agent.run("Goal test")

    assert report.status == JobStatus.ESCALATED
    assert any("failed to submit structured plan" in b.description for b in report.blockers)


@pytest.mark.asyncio
async def test_progress_update_failure_does_not_crash(sandbox_with_tmp):
    """If store.update_job_progress raises, the loop keeps running."""
    provider = ScriptedProvider([
        _plan_response(["pytest test.py"]),
        _write_response("f1.py", "def foo():\n    return 42\n"),
        _empty_response(),
    ])
    sandbox_with_tmp.execute.return_value = (0, b"OK", b"")

    failing_store = AsyncMock()
    failing_store.update_job_progress.side_effect = RuntimeError("db down")

    agent = ChrysalideAgent(
        provider=provider,
        sandbox=sandbox_with_tmp,
        job_id="test_progress",
        store=failing_store,
        budget=Budget(),
    )
    report = await agent.run("Goal test")

    assert report.status == JobStatus.DONE
    # progress was attempted at least once
    assert failing_store.update_job_progress.await_count >= 1


@pytest.mark.asyncio
async def test_files_changed_uses_real_hash(sandbox_with_tmp, mock_store):
    """The hash in files_changed must match sha256 of the actual file content."""
    import hashlib
    content = "def foo():\n    return 42\n"
    provider = ScriptedProvider([
        _plan_response(["pytest test.py"]),
        _write_response("f1.py", content),
        _empty_response(),
    ])
    sandbox_with_tmp.execute.return_value = (0, b"OK", b"")

    agent = ChrysalideAgent(
        provider=provider,
        sandbox=sandbox_with_tmp,
        job_id="test_hash",
        store=mock_store,
        budget=Budget(),
    )
    report = await agent.run("Goal test")

    expected_hash = hashlib.sha256(content.encode()).hexdigest()
    assert report.files_changed[0].hash == f"sha256:{expected_hash}"
