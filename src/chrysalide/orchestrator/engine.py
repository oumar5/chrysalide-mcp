import asyncio
import logging
from typing import Dict, Any, Optional

from chrysalide.models import JobConfig
from chrysalide.orchestrator.store import JobStore
from chrysalide.sandbox import GitWorktreeSandbox
from chrysalide.agent import ChrysalideAgent
from chrysalide.providers import get_default_provider

logger = logging.getLogger(__name__)

class ChrysalideEngine:
    def __init__(self, store: JobStore):
        self.store = store
        
    async def run_job_background(self, job_id: str, request: JobConfig):
        try:
            await self.store.update_job(job_id, status="running")
            
            provider = get_default_provider()
            
            async with GitWorktreeSandbox(str(request.repo_path), persist=False) as sandbox:
                agent = ChrysalideAgent(provider, sandbox)
                
                system_prompt = (
                    "Tu es Chrysalide, un agent de codage asynchrone autonome. "
                    "Tu opères dans un espace de travail git (sandbox). "
                    "Tu as accès aux outils pour lire/écrire des fichiers et exécuter des commandes shell ou git. "
                    "Utilise ces outils pour accomplir la tâche suivante. "
                    "Lorsque la tâche est terminée, cesse d'appeler des outils pour terminer ton exécution."
                )
                
                result = await agent.run(request.goal, system_prompt)
                
                final_status = result.get("status", "failed")
                await self.store.update_job(job_id, status=final_status, result=result)
                
        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}")
            await self.store.update_job(job_id, status="failed", result={"error": str(e)})

    async def start_job(self, request: JobConfig) -> str:
        job_id = await self.store.create_job(request)
        asyncio.create_task(self.run_job_background(job_id, request))
        return job_id
