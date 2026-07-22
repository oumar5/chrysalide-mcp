import os
import time
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from chrysalide.models import (
    ReportPayload, FileChanged, CommandExecuted, 
    Decision, Blocker, Finding, Budget, JobStatus, FindingType
)
from chrysalide.providers.base import WorkerProvider
from chrysalide.sandbox import GitWorktreeSandbox
from chrysalide.agent.tools import ToolRegistry
from chrysalide.agent.state import AgentState

logger = logging.getLogger(__name__)

class ChrysalideAgent:
    """Agent orchestrateur implémentant la boucle à 4 phases (PLAN, ACT, VALIDATE, CORRECT)."""
    
    def __init__(
        self,
        provider: WorkerProvider,
        sandbox: GitWorktreeSandbox,
        job_id: str,
        store: Any,
        budget: Budget,
        constraints: Optional[str] = None
    ):
        self.provider = provider
        self.sandbox = sandbox
        self.job_id = job_id
        self.store = store
        self.budget = budget
        self.constraints = constraints or "Aucune contrainte particulière."
        
        self.tools = ToolRegistry(sandbox)
        self.state = AgentState()
        
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
            # Pousser l'avancement
            from chrysalide.models import JobProgress
            prog = JobProgress(
                current_iteration=self.state.iterations,
                max_iterations=self.budget.max_iterations,
                current_phase=self.state.current_phase,
                wall_time_sec=time.time() - self.state.start_time
            )
            import asyncio
            asyncio.create_task(self.store.update_job_progress(self.job_id, prog))
            
            # 1. Vérification des budgets
            budget_check = self._check_budgets()
            if budget_check:
                return self._generate_report(JobStatus.ESCALATED, blockers=[Blocker(description=budget_check, resolution="escalated", detail="Budget dépassé.")])
                
            logger.info(f"Début phase {self.state.current_phase} (Iter: {self.state.iterations})")
            
            try:
                if self.state.current_phase == "PLAN":
                    status = await self._run_plan()
                    if status != "CONTINUE":
                        return self._generate_report(status)
                    self.state.current_phase = "ACT"
                    
                elif self.state.current_phase == "ACT":
                    status = await self._run_act()
                    if status != "CONTINUE":
                        return self._generate_report(status)
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
                logger.error(f"Agent crasché: {e}", exc_info=True)
                return self._generate_report(JobStatus.FAILED, error={"type": type(e).__name__, "message": str(e)})

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
            tools=tools
        )
        
        self.state.tokens_input += response.tokens_input
        self.state.tokens_output += response.tokens_output
        
        assistant_msg = response.content or ""
        if response.tool_calls:
            assistant_msg += f"\n[Appels: {', '.join(t['name'] for t in response.tool_calls)}]"
        self.state.add_message("assistant", assistant_msg)
        
        self.state.iteration_log.append(Finding(
            type=FindingType.NOTE,
            data={"phase": self.state.current_phase, "input": prompt, "response": assistant_msg, "tool_calls": len(response.tool_calls)}
        ))
        return response

    async def _run_plan(self) -> str:
        plan_prompt = self._load_prompt("plan.md").format(
            goal=self.goal, 
            constraints=self.constraints
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
                                    "files": {"type": "array", "items": {"type": "string"}}
                                },
                                "required": ["title", "files"]
                            }
                        },
                        "validation_commands": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "risks": {
                            "type": "array",
                            "items": {"type": "string"}
                        }
                    },
                    "required": ["subtasks", "validation_commands", "risks"]
                }
            }
        }]
        
        response = await self._call_llm(plan_prompt, tools=plan_tools)
        
        for tc in response.tool_calls:
            if tc.get("name") == "submit_plan":
                args = tc.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except:
                        args = {}
                self.state.plan = args
                self.state.iteration_log.append(Finding(type=FindingType.PLAN, data=args))
                return "CONTINUE"
                
        # If no plan submitted, fallback to parse json blocks or just record it
        self.state.blockers.append(Blocker(description="LLM failed to submit structured plan", resolution="unresolved", detail=response.content))
        return "escalated"

    async def _run_act(self) -> str:
        act_prompt = self._load_prompt("act.md").format(
            goal=self.goal,
            plan=json.dumps(self.state.plan, indent=2) if self.state.plan else "Aucun plan"
        )
        
        tool_defs = self.tools.get_definitions()
        
        # Max 5 tool steps per ACT phase
        for _ in range(5):
            response = await self._call_llm(act_prompt, tools=tool_defs)
            if not response.tool_calls:
                break
                
            tool_results = []
            for tc in response.tool_calls:
                t_name = tc.get("name", "")
                t_args = tc.get("arguments", {})
                if isinstance(t_args, str):
                    try:
                        t_args = json.loads(t_args)
                    except:
                        pass
                
                try:
                    res = await self.tools.execute(t_name, t_args)
                    if t_name == "fs.write" and "path" in t_args:
                        # Tracker les fichiers changés
                        self._track_file_changed(t_args["path"], "modified")
                except Exception as e:
                    res = f"Tool exec error: {str(e)}"
                    
                tool_results.append(f"Result for {t_name}:\n{res}")
                
            act_prompt = "\n---\n".join(tool_results)
            
        return "CONTINUE"

    def _track_file_changed(self, path: str, action: str):
        # TODO: Get real hash/lines from sandbox
        self.state.files_changed.append(FileChanged(
            path=path,
            action=action,
            lines=0,
            hash="000000",
            size_bytes=0
        ))

    async def _run_validate(self) -> str:
        if not self.state.plan or "validation_commands" not in self.state.plan:
            return "SUCCESS" # Rien à valider
            
        cmds = self.state.plan["validation_commands"]
        all_passed = True
        
        for cmd in cmds:
            start_t = time.time()
            returncode, stdout, stderr = await self.sandbox.execute(cmd)
            duration = time.time() - start_t
            
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
                truncated=truncated
            )
            self.state.commands_executed.append(exec_record)
            
            if returncode != 0:
                all_passed = False
                
        if all_passed:
            return "SUCCESS"
        else:
            return "CORRECT"

    async def _run_correct(self) -> str:
        # Get last validation errors
        failures = [c for c in self.state.commands_executed if c.phase == "VALIDATE" and c.iteration == self.state.iterations and c.exit_code != 0]
        
        errors_text = ""
        for f in failures:
            errors_text += f"\nCommand: {f.cmd}\nExit Code: {f.exit_code}\nStdout: {f.stdout_tail}\nStderr: {f.stderr_tail}\n"
            
        # Détection de boucle
        sig = str(hash(errors_text))
        if self.state.error_signatures.count(sig) >= 2:
            self.state.blockers.append(Blocker(
                description="Boucle d'erreur détectée",
                resolution="escalated",
                detail=errors_text[:200]
            ))
            return "escalated"
            
        self.state.error_signatures.append(sig)
        
        correct_prompt = self._load_prompt("correct.md").format(errors=errors_text)
        
        response = await self._call_llm(correct_prompt, tools=self.tools.get_definitions())
        
        # We can execute tools here if they call it, but typically they analyze and maybe run an explore command.
        if response.tool_calls:
            # For simplicity, if they call tools here, we run them.
            tool_results = []
            for tc in response.tool_calls:
                t_name = tc.get("name", "")
                t_args = tc.get("arguments", {})
                if isinstance(t_args, str):
                    try:
                        t_args = json.loads(t_args)
                    except:
                        pass
                try:
                    res = await self.tools.execute(t_name, t_args)
                except Exception as e:
                    res = str(e)
                tool_results.append(f"Result {t_name}:\n{res}")
            self.state.add_message("user", "\n".join(tool_results))
            
        return "CONTINUE"

    def _generate_report(self, status: JobStatus, error: Optional[Dict[str, str]] = None, blockers: Optional[List[Blocker]] = None) -> ReportPayload:
        if blockers:
            self.state.blockers.extend(blockers)
            
        # Get file stats properly
        # TODO: Ideally we'd call sandbox.execute("git status") to get real diffs. For now we use the tracked ones.
        
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
            tokens_used={
                "input": self.state.tokens_input,
                "output": self.state.tokens_output,
                "total": self.state.tokens_input + self.state.tokens_output
            },
            provider={"name": provider_info.get("name", ""), "model": provider_info.get("model", "")},
            plan=self.state.plan,
            files_changed=self.state.files_changed,
            diff_summary={
                "files": len(self.state.files_changed),
                "added": len([f for f in self.state.files_changed if f.action == "created"]),
                "removed": len([f for f in self.state.files_changed if f.action == "deleted"])
            },
            commands_executed=self.state.commands_executed,
            decisions=self.state.decisions,
            blockers=self.state.blockers,
            iteration_log=self.state.iteration_log,
            sandbox_path=self.sandbox.worktree_path,
            integration_hint=f"git merge chrysalide/{self.job_id}" if status == JobStatus.DONE else None,
            error=error
        )
