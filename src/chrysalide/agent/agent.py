import re
import time
import json
import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone

from chrysalide.models import (
    ReportPayload, FileChanged, CommandExecuted,
    Blocker, Finding, Budget, JobStatus, FindingType,
    TokenUsage, ProviderInfo, DiffSummary, JobProgress
)
from chrysalide.providers.base import WorkerProvider
from chrysalide.sandbox import GitWorktreeSandbox
from chrysalide.agent.tools import ToolRegistry
from chrysalide.agent.state import AgentState

logger = logging.getLogger(__name__)

# Anti-optimism regex patterns applied to Python source only.
_STUB_PATTERNS = [
    (re.compile(r"^\s*pass\s*(#.*)?$", re.MULTILINE), "empty pass body"),
    (re.compile(r"raise\s+NotImplementedError"), "NotImplementedError stub"),
    (re.compile(r"#\s*TODO", re.IGNORECASE), "TODO marker"),
    (re.compile(r"#\s*FIXME", re.IGNORECASE), "FIXME marker"),
    (re.compile(r"@pytest\.mark\.skip"), "disabled test (pytest.mark.skip)"),
]

# Files exempted from anti-optimism checks (config, docs, etc.).
_STUB_CHECK_SUFFIXES = {".py"}


class ChrysalideAgent:
    """Agent orchestrateur implémentant la boucle à 4 phases (PLAN, ACT, VALIDATE, CORRECT)."""

    def __init__(
        self,
        provider: WorkerProvider,
        sandbox: GitWorktreeSandbox,
        job_id: str,
        store: Any,
        budget: Budget,
        constraints: Optional[str] = None,
        loop_detection_threshold: int = 3,
    ):
        self.provider = provider
        self.sandbox = sandbox
        self.job_id = job_id
        self.store = store
        self.budget = budget
        self.constraints = constraints or "Aucune contrainte particulière."
        self.loop_detection_threshold = loop_detection_threshold

        self.tools = ToolRegistry(sandbox)
        self.state = AgentState()
        # path -> initial hash (None if file didn't exist before agent touched it)
        self._file_baselines: Dict[str, Optional[str]] = {}

    def _load_prompt(self, filename: str) -> str:
        prompt_path = Path(__file__).parent / "prompts" / filename
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()

    async def run(self, goal: str) -> ReportPayload:
        """Exécute l'agent sur le but donné en passant par les 4 phases."""
        self.goal = goal
        self.system_prompt = self._load_prompt("system.md")
        self.state.current_phase = "PLAN"

        while True:
            await self._push_progress()

            budget_check = self._check_budgets()
            if budget_check:
                return self._generate_report(
                    JobStatus.ESCALATED,
                    blockers=[Blocker(description=budget_check, resolution="escalated", detail="Budget dépassé.")],
                )

            logger.info(f"Début phase {self.state.current_phase} (Iter: {self.state.iterations})")

            try:
                if self.state.current_phase == "PLAN":
                    status = await self._run_plan()
                    if status != "CONTINUE":
                        return self._generate_report(JobStatus.ESCALATED)
                    self.state.current_phase = "ACT"

                elif self.state.current_phase == "ACT":
                    status = await self._run_act()
                    if status != "CONTINUE":
                        return self._generate_report(JobStatus.ESCALATED)
                    self.state.current_phase = "VALIDATE"

                elif self.state.current_phase == "VALIDATE":
                    status = await self._run_validate()
                    if status == "SUCCESS":
                        return self._generate_report(JobStatus.DONE)
                    elif status == "CORRECT":
                        self.state.current_phase = "CORRECT"
                    else:
                        return self._generate_report(JobStatus.ESCALATED)

                elif self.state.current_phase == "CORRECT":
                    status = await self._run_correct()
                    if status != "CONTINUE":
                        return self._generate_report(JobStatus.ESCALATED)
                    self.state.current_phase = "ACT"
            except Exception as e:
                logger.error(f"Agent crashed: {e}", exc_info=True)
                return self._generate_report(
                    JobStatus.FAILED,
                    error={"type": type(e).__name__, "message": str(e)},
                )

    async def _push_progress(self) -> None:
        """Push a live progress snapshot; log failures but don't crash the loop."""
        prog = JobProgress(
            current_iteration=self.state.iterations,
            max_iterations=self.budget.max_iterations,
            current_phase=self.state.current_phase,
            wall_time_sec=time.time() - self.state.start_time,
        )
        try:
            await self.store.update_progress(self.job_id, prog)
        except Exception as e:
            logger.warning(f"Failed to update job progress for {self.job_id}: {e}")

    def _check_budgets(self) -> Optional[str]:
        if self.state.iterations >= self.budget.max_iterations:
            return "max_iterations atteint"
        elapsed_min = (time.time() - self.state.start_time) / 60.0
        if elapsed_min >= self.budget.max_wall_time_min:
            return "max_wall_time_min atteint"
        if (self.state.tokens_input + self.state.tokens_output) >= self.budget.max_tokens_total:
            return "max_tokens_total atteint"
        return None

    async def _call_llm(self, prompt: str, tools: Optional[List[Dict[str, Any]]] = None) -> Any:
        self.state.iterations += 1
        self.state.add_message("user", prompt)

        response = await self.provider.complete(
            system_prompt=self.system_prompt,
            messages=self.state.messages,
            tools=tools,
        )

        self.state.tokens_input += response.tokens_input
        self.state.tokens_output += response.tokens_output

        assistant_msg = response.content or ""
        if response.tool_calls:
            assistant_msg += f"\n[Appels: {', '.join(t['name'] for t in response.tool_calls)}]"
        self.state.add_message("assistant", assistant_msg)

        return response

    async def _run_plan(self) -> str:
        plan_prompt = self._load_prompt("plan.md").format(
            goal=self.goal,
            constraints=self.constraints,
        )

        plan_tools = [{
            "type": "function",
            "function": {
                "name": "submit_plan",
                "description": "Soumet le plan d'action décomposé.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "subtasks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "files": {"type": "array", "items": {"type": "string"}},
                                },
                                "required": ["title", "files"],
                            },
                        },
                        "validation_commands": {"type": "array", "items": {"type": "string"}},
                        "risks": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["subtasks", "validation_commands", "risks"],
                },
            },
        }]

        response = await self._call_llm(plan_prompt, tools=plan_tools)

        for tc in response.tool_calls or []:
            if tc.get("name") == "submit_plan":
                args = tc.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                self.state.plan = args
                self.state.iteration_log.append(Finding(type=FindingType.PLAN, data=args))
                return "CONTINUE"

        self.state.blockers.append(
            Blocker(
                description="LLM failed to submit structured plan",
                resolution="unresolved",
                detail=(response.content or "")[:500],
            )
        )
        return "ESCALATE"

    async def _run_act(self) -> str:
        act_prompt = self._load_prompt("act.md").format(
            goal=self.goal,
            plan=json.dumps(self.state.plan, indent=2) if self.state.plan else "Aucun plan",
        )

        tool_defs = self.tools.get_definitions()
        prompt = act_prompt

        # Cap tool-use steps per ACT phase to avoid runaway; each step counts against iterations.
        for _ in range(5):
            response = await self._call_llm(prompt, tools=tool_defs)
            if not response.tool_calls:
                break

            tool_results: List[str] = []
            for tc in response.tool_calls:
                t_name = tc.get("name", "")
                t_args = tc.get("arguments", {})
                if isinstance(t_args, str):
                    try:
                        t_args = json.loads(t_args)
                    except json.JSONDecodeError:
                        t_args = {}

                # Capture baseline BEFORE executing write, so we can detect created vs modified.
                if t_name == "write_file" and "path" in t_args:
                    await self._capture_baseline(t_args["path"])

                try:
                    res = await self.tools.execute(t_name, t_args)
                except Exception as e:
                    res = f"Tool exec error: {e}"

                # After a write, refresh the file record with real stats.
                if t_name == "write_file" and "path" in t_args:
                    await self._record_file_change(t_args["path"])

                tool_results.append(f"Result for {t_name}:\n{res}")

            prompt = "\n---\n".join(tool_results)

        # Anti-optimism: after ACT, scan changed source files for stubs.
        stub_findings = await self._scan_for_stubs()
        if stub_findings:
            summary = "; ".join(f"{path}: {reason}" for path, reason in stub_findings)
            self.state.blockers.append(
                Blocker(
                    description="Anti-optimism check: stubs detected in written code",
                    resolution="unresolved",
                    detail=summary,
                )
            )
            self.state.iteration_log.append(
                Finding(
                    type=FindingType.CORRECTION_HYPOTHESIS,
                    data={"reason": "stubs detected", "findings": summary},
                )
            )
            return "ESCALATE"

        return "CONTINUE"

    async def _capture_baseline(self, path: str) -> None:
        """Record the initial hash (or None if absent) for a file about to be written."""
        if path in self._file_baselines:
            return
        full_path = self.sandbox.get_path() / path
        if full_path.exists() and full_path.is_file():
            try:
                self._file_baselines[path] = self._hash_file(full_path)
            except OSError:
                self._file_baselines[path] = None
        else:
            self._file_baselines[path] = None

    async def _record_file_change(self, path: str) -> None:
        """Compute real (lines, hash, size, action) for a file after a write."""
        full_path = self.sandbox.get_path() / path
        if not full_path.exists() or not full_path.is_file():
            return

        try:
            content_bytes = full_path.read_bytes()
        except OSError as e:
            logger.warning(f"Failed to read {path} after write: {e}")
            return

        lines = content_bytes.count(b"\n") + (1 if content_bytes and not content_bytes.endswith(b"\n") else 0)
        new_hash = hashlib.sha256(content_bytes).hexdigest()
        size_bytes = len(content_bytes)
        baseline = self._file_baselines.get(path)
        action = "created" if baseline is None else "modified"

        # Replace any prior entry for this path (latest state wins).
        self.state.files_changed = [f for f in self.state.files_changed if f.path != path]
        self.state.files_changed.append(
            FileChanged(
                path=path,
                action=action,
                lines=lines,
                hash=f"sha256:{new_hash}",
                size_bytes=size_bytes,
            )
        )
        self.state.iteration_log.append(
            Finding(
                type=FindingType.FILE_WRITE,
                data={"path": path, "action": action, "lines": lines, "hash": f"sha256:{new_hash}", "size_bytes": size_bytes},
            )
        )

    @staticmethod
    def _hash_file(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    async def _scan_for_stubs(self) -> List[Tuple[str, str]]:
        """Return [(path, reason), ...] for stub markers found in changed source files."""
        findings: List[Tuple[str, str]] = []
        for fc in self.state.files_changed:
            if Path(fc.path).suffix not in _STUB_CHECK_SUFFIXES:
                continue
            full_path = self.sandbox.get_path() / fc.path
            if not full_path.exists():
                continue
            try:
                text = full_path.read_text(errors="replace")
            except OSError:
                continue
            for pattern, reason in _STUB_PATTERNS:
                if pattern.search(text):
                    findings.append((fc.path, reason))
                    break
        return findings

    async def _run_validate(self) -> str:
        if not self.state.plan or "validation_commands" not in self.state.plan:
            return "SUCCESS"

        cmds = self.state.plan["validation_commands"] or []
        if not cmds:
            return "SUCCESS"

        all_passed = True

        for cmd in cmds:
            start_t = time.time()
            returncode, stdout, stderr = await self.sandbox.execute(cmd)
            duration = time.time() - start_t

            # Sandbox may return bytes or str depending on backend/mocks.
            if isinstance(stdout, (bytes, bytearray)):
                stdout = stdout.decode(errors="replace")
            if isinstance(stderr, (bytes, bytearray)):
                stderr = stderr.decode(errors="replace")

            truncated = False
            if len(stdout) > 4000:
                stdout = stdout[-4000:]
                truncated = True
            if len(stderr) > 4000:
                stderr = stderr[-4000:]
                truncated = True

            exec_record = CommandExecuted(
                phase="VALIDATE",
                iteration=self.state.iterations,
                cmd=cmd,
                exit_code=returncode,
                duration_sec=duration,
                stdout_tail=stdout,
                stderr_tail=stderr,
                truncated=truncated,
            )
            self.state.commands_executed.append(exec_record)
            self.state.iteration_log.append(
                Finding(
                    type=FindingType.COMMAND_RUN,
                    data={
                        "cmd": cmd,
                        "exit_code": returncode,
                        "duration_sec": duration,
                        "phase": "VALIDATE",
                    },
                )
            )

            if returncode != 0:
                all_passed = False

        if all_passed:
            self.state.iteration_log.append(
                Finding(type=FindingType.VALIDATION_SUCCESS, data={"commands": len(cmds)})
            )
            return "SUCCESS"
        return "CORRECT"

    async def _run_correct(self) -> str:
        # Collect failures from the latest VALIDATE round.
        failures = [
            c for c in self.state.commands_executed
            if c.phase == "VALIDATE" and c.iteration == self.state.iterations and c.exit_code != 0
        ]

        errors_text = ""
        for f in failures:
            errors_text += f"\nCommand: {f.cmd}\nExit Code: {f.exit_code}\nStdout: {f.stdout_tail}\nStderr: {f.stderr_tail}\n"

        # Loop detection: if the same error signature has appeared N times already, escalate.
        sig = hashlib.sha256(errors_text.encode("utf-8")).hexdigest()
        prior_occurrences = self.state.error_signatures.count(sig)
        self.state.error_signatures.append(sig)
        if prior_occurrences + 1 >= self.loop_detection_threshold:
            self.state.blockers.append(
                Blocker(
                    description="Boucle d'erreur détectée",
                    resolution="escalated",
                    detail=errors_text[:500],
                )
            )
            self.state.iteration_log.append(
                Finding(
                    type=FindingType.CORRECTION_HYPOTHESIS,
                    data={"reason": "loop_detected", "signature": sig, "occurrences": prior_occurrences + 1},
                )
            )
            return "ESCALATE"

        correct_prompt = self._load_prompt("correct.md").format(errors=errors_text)
        response = await self._call_llm(correct_prompt, tools=self.tools.get_definitions())

        self.state.iteration_log.append(
            Finding(
                type=FindingType.CORRECTION_HYPOTHESIS,
                data={"reason": "analysis", "content_tail": (response.content or "")[-500:]},
            )
        )

        # Execute any exploration tools the LLM chose to call during CORRECT.
        if response.tool_calls:
            tool_results: List[str] = []
            for tc in response.tool_calls:
                t_name = tc.get("name", "")
                t_args = tc.get("arguments", {})
                if isinstance(t_args, str):
                    try:
                        t_args = json.loads(t_args)
                    except json.JSONDecodeError:
                        t_args = {}
                try:
                    res = await self.tools.execute(t_name, t_args)
                except Exception as e:
                    res = str(e)
                tool_results.append(f"Result {t_name}:\n{res}")
            self.state.add_message("user", "\n".join(tool_results))

        return "CONTINUE"

    def _generate_report(
        self,
        status: JobStatus,
        error: Optional[Dict[str, str]] = None,
        blockers: Optional[List[Blocker]] = None,
    ) -> ReportPayload:
        if blockers:
            self.state.blockers.extend(blockers)

        provider_info = self.provider.get_info()

        return ReportPayload(
            job_id=self.job_id,
            status=status,
            summary=f"Agent a terminé avec le statut {status}.",
            goal=self.goal,
            created_at=datetime.fromtimestamp(self.state.start_time, tz=timezone.utc),
            completed_at=datetime.now(timezone.utc),
            iterations_used=self.state.iterations,
            iterations_max=self.budget.max_iterations,
            wall_time_sec=time.time() - self.state.start_time,
            tokens_used=TokenUsage(
                input=self.state.tokens_input,
                output=self.state.tokens_output,
                total=self.state.tokens_input + self.state.tokens_output,
            ),
            provider=ProviderInfo(
                name=provider_info.get("name") or provider_info.get("provider") or "",
                model=provider_info.get("model", ""),
            ),
            plan=self.state.plan,
            files_changed=self.state.files_changed,
            diff_summary=DiffSummary(
                files=len(self.state.files_changed),
                added=sum(f.lines for f in self.state.files_changed if f.action == "created"),
                removed=0,
            ),
            commands_executed=self.state.commands_executed,
            decisions=self.state.decisions,
            blockers=self.state.blockers,
            iteration_log=self.state.iteration_log,
            sandbox_path=str(self.sandbox.worktree_path),
            integration_hint=f"git merge chrysalide/{self.job_id}" if status == JobStatus.DONE else None,
            error=error,
        )
