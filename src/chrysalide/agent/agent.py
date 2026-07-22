import os
import time
import logging
from typing import List, Dict, Any, Optional

from chrysalide.providers.base import WorkerProvider
from chrysalide.sandbox import GitWorktreeSandbox
from chrysalide.agent.tools import ToolRegistry
from chrysalide.agent.state import AgentState

logger = logging.getLogger(__name__)

class ChrysalideAgent:
    """Agent orchestrateur qui boucle entre LLM et outils."""
    def __init__(
        self,
        provider: WorkerProvider,
        sandbox: GitWorktreeSandbox,
        max_iterations: int = 15,
        max_wall_time_min: int = 30,
        max_tokens_total: int = 500000
    ):
        self.provider = provider
        self.sandbox = sandbox
        self.tools = ToolRegistry(sandbox)
        
        self.max_iterations = max_iterations
        self.max_wall_time_min = max_wall_time_min
        self.max_tokens_total = max_tokens_total
        self.state = AgentState()
        
    async def run(self, goal: str, system_prompt: str) -> Dict[str, Any]:
        """Exécute l'agent sur le but donné, jusqu'à complétion ou erreur/limite."""
        
        self.state.add_message("user", goal)
        tool_defs = self.tools.get_definitions()
        
        while True:
            # 1. Vérification des budgets
            if self.state.iterations >= self.max_iterations:
                return {"status": "escalated", "reason": "max_iterations atteint", "state": self.state.model_dump()}
                
            elapsed_min = (time.time() - self.state.start_time) / 60.0
            if elapsed_min >= self.max_wall_time_min:
                return {"status": "escalated", "reason": "max_wall_time_min atteint", "state": self.state.model_dump()}
                
            if (self.state.tokens_input + self.state.tokens_output) >= self.max_tokens_total:
                return {"status": "escalated", "reason": "max_tokens_total atteint", "state": self.state.model_dump()}
                
            # 2. Appel au provider
            self.state.iterations += 1
            logger.info(f"Iteration {self.state.iterations} démarrée.")
            
            try:
                response = await self.provider.complete(
                    system_prompt=system_prompt,
                    messages=self.state.messages,
                    tools=tool_defs
                )
            except Exception as e:
                logger.error(f"Erreur provider: {e}")
                return {"status": "failed", "error": str(e), "state": self.state.model_dump()}
                
            self.state.tokens_input += response.tokens_input
            self.state.tokens_output += response.tokens_output
            
            # Ajouter la réponse au state
            assistant_msg = response.content
            if not assistant_msg and response.tool_calls:
                assistant_msg = f"[Appel d'outils: {', '.join(t['name'] for t in response.tool_calls)}]"
            
            self.state.add_message("assistant", assistant_msg)
            
            # Condition d'arrêt simple: pas d'outils appelés = succès / terminé.
            if not response.tool_calls:
                return {"status": "success", "content": response.content, "state": self.state.model_dump()}
                
            # 3. Exécution des tools
            tool_results = []
            for tc in response.tool_calls:
                t_name = tc.get("name", "")
                t_args = tc.get("arguments", {})
                
                try:
                    res = await self.tools.execute(t_name, t_args)
                except Exception as e:
                    res = f"Tool exec error: {str(e)}"
                    
                tool_results.append(f"Result for {t_name}:\n{res}")
                
            self.state.add_message("user", "\n---\n".join(tool_results))
