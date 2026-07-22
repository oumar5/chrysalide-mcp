import time
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from chrysalide.models import FileChanged, CommandExecuted, Decision, Blocker, Finding

class AgentState(BaseModel):
    """État interne de l'agent pendant une boucle."""
    messages: List[Dict[str, str]] = []
    iterations: int = 0
    start_time: float = Field(default_factory=time.time)
    tokens_input: int = 0
    tokens_output: int = 0
    
    # 4 phases variables
    current_phase: str = "PLAN"  # PLAN, ACT, VALIDATE, CORRECT
    plan: Optional[Dict[str, Any]] = None
    
    # Tracking for ReportPayload
    files_changed: List[FileChanged] = []
    commands_executed: List[CommandExecuted] = []
    decisions: List[Decision] = []
    blockers: List[Blocker] = []
    iteration_log: List[Finding] = []
    
    # Loop detection for escalation
    error_signatures: List[str] = []
    
    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
