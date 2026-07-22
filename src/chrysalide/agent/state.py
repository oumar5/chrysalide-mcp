import time
from typing import List, Dict, Any
from pydantic import BaseModel, Field

class AgentState(BaseModel):
    """État interne de l'agent pendant une boucle."""
    messages: List[Dict[str, str]] = []
    iterations: int = 0
    start_time: float = Field(default_factory=time.time)
    tokens_input: int = 0
    tokens_output: int = 0
    
    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
