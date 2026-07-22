import asyncio
import logging
from typing import Dict, Any, Optional
from pathlib import Path

from chrysalide.models import JobConfig, JobStatus, ReportPayload
from chrysalide.orchestrator.store import JobStore
from chrysalide.sandbox import GitWorktreeSandbox
from chrysalide.agent.agent import ChrysalideAgent
from chrysalide.providers import get_default_provider

logger = logging.getLogger(__name__)

class ChrysalideEngine:
    def __init__(self, store: JobStore):
        self.store = store
        self.tasks: Dict[str, asyncio.Task] = {}
        
    async def run_job_background(self, job_id: str, request: JobConfig):
        try:
            await self.store.update_job(job_id, JobStatus.RUNNING)
            
            provider = get_default_provider()
            
            async with GitWorktreeSandbox(str(request.repo_path), job_id=job_id, persist=True, allow_network=request.allow_network) as sandbox:
                agent = ChrysalideAgent(
                    provider=provider, 
                    sandbox=sandbox,
                    job_id=job_id,
                    store=self.store,
                    budget=request.budget,
                    constraints=request.constraints
                )
                
                # The agent handles the 4 phases and returns the ReportPayload
                report = await agent.run(request.goal)
                
                final_status = JobStatus(report.status)
                await self.store.update_report(job_id, report)
                await self.store.update_job(job_id, final_status)
                
        except asyncio.CancelledError:
            logger.info(f"Job {job_id} cancelled.")
            await self.store.update_job(job_id, JobStatus.CANCELLED)
        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}")
            await self.store.update_job(job_id, JobStatus.FAILED)
        finally:
            if job_id in self.tasks:
                del self.tasks[job_id]

    async def start_job(self, request: JobConfig) -> str:
        job_id = await self.store.create_job(request)
        task = asyncio.create_task(self.run_job_background(job_id, request))
        self.tasks[job_id] = task
        return job_id

    async def cancel_job(self, job_id: str, reason: str = "") -> bool:
        if job_id in self.tasks:
            self.tasks[job_id].cancel()
            return True
        return False
