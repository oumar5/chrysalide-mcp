import os
import asyncio
import logging
from typing import Dict, Any

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types

from chrysalide.models import JobConfig, JobStatus, StartTaskResponse, GetStatusResponse, GetReportResponse, CancelTaskResponse
from chrysalide.orchestrator.store import JobStore
from chrysalide.orchestrator.engine import ChrysalideEngine

logger = logging.getLogger(__name__)

store = JobStore()
engine = ChrysalideEngine(store)

server = Server("chrysalide-mcp")

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="chrysalide_start_task",
            description="Démarre un nouveau job Chrysalide. Retourne immédiatement avec un job_id.",
            inputSchema={
                "type": "object",
                "properties": {
                    "goal": {"type": "string", "description": "Consigne de feature, explicite et complète"},
                    "repo_path": {"type": "string", "description": "Chemin absolu du repo cible (doit être un repo git)"},
                    "base_branch": {"type": "string", "description": "Branche de base pour créer le worktree (défaut: main)"},
                    "constraints": {"type": "array", "items": {"type": "string"}, "description": "Contraintes techniques libres"},
                    "budget.max_iterations": {"type": "integer", "description": "Nombre max d'itérations de la boucle"},
                    "budget.max_wall_time_min": {"type": "integer", "description": "Timeout global en minutes"},
                    "budget.max_tokens_total": {"type": "integer", "description": "Budget de tokens total (input+output)"},
                    "provider_override": {"type": "string", "description": "Force un provider pour ce job. Format <provider>:<model>"},
                    "allow_network": {"type": "boolean", "description": "Autorise l'accès réseau depuis la sandbox"}
                },
                "required": ["goal", "repo_path"]
            }
        ),
        types.Tool(
            name="chrysalide_get_status",
            description="Retourne l'état courant d'un job. Non-bloquant.",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "L'identifiant du job"}
                },
                "required": ["job_id"]
            }
        ),
        types.Tool(
            name="chrysalide_get_report",
            description="Retourne le rapport final. À appeler seulement quand le job est terminé.",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "L'identifiant du job"},
                    "format": {"type": "string", "description": "Format du rapport (json, markdown, both)", "default": "both"}
                },
                "required": ["job_id"]
            }
        ),
        types.Tool(
            name="chrysalide_cancel_task",
            description="Annule un job en cours. La sandbox est conservée pour inspection.",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "L'identifiant du job à annuler"},
                    "reason": {"type": "string", "description": "Raison de l'annulation"}
                },
                "required": ["job_id"]
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        if name == "chrysalide_start_task":
            goal = arguments.get("goal")
            repo_path = arguments.get("repo_path")
            
            if not repo_path or not goal:
                return [types.TextContent(type="text", text="Error: repo_path and goal are required.")]
                
            req = JobConfig(repo_path=repo_path, goal=goal)
            
            # Optional overrides
            if "base_branch" in arguments: req.base_branch = arguments["base_branch"]
            if "constraints" in arguments: req.constraints = arguments["constraints"]
            if "provider_override" in arguments: req.provider_override = arguments["provider_override"]
            if "allow_network" in arguments: req.allow_network = arguments["allow_network"]
            
            job_id = await engine.start_job(req)
            return [types.TextContent(type="text", text=StartTaskResponse(job_id=job_id).model_dump_json(indent=2))]
            
        elif name == "chrysalide_get_status":
            job_id = arguments.get("job_id")
            if not job_id:
                return [types.TextContent(type="text", text="Error: job_id is required.")]
                
            job = await store.get_job(job_id)
            if not job:
                return [types.TextContent(type="text", text=f"Error: JOB_NOT_FOUND - {job_id}")]
                
            is_ready = job.status in [JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.ESCALATED]
            
            status_dict = {
                "job_id": job.job_id,
                "status": job.status,
                "progress": job.progress.model_dump(),
                "report_ready": is_ready
            }
            import json
            return [types.TextContent(type="text", text=json.dumps(status_dict, indent=2))]
            
        elif name == "chrysalide_get_report":
            job_id = arguments.get("job_id")
            if not job_id:
                return [types.TextContent(type="text", text="Error: job_id is required.")]
                
            job = await store.get_job(job_id)
            if not job:
                return [types.TextContent(type="text", text=f"Error: JOB_NOT_FOUND - {job_id}")]
                
            is_ready = job.status in [JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.ESCALATED]
            if not is_ready:
                return [types.TextContent(type="text", text="Error: REPORT_NOT_READY - Le job est encore en cours.")]
                
            if not job.report:
                return [types.TextContent(type="text", text="Error: REPORT_NOT_READY - Aucun rapport n'a été généré.")]
                
            # TODO: handle 'format' (json vs markdown vs both). Currently just dumping JSON
            return [types.TextContent(type="text", text=job.report.model_dump_json(indent=2))]

        elif name == "chrysalide_cancel_task":
            job_id = arguments.get("job_id")
            if not job_id:
                return [types.TextContent(type="text", text="Error: job_id is required.")]
                
            job = await store.get_job(job_id)
            if not job:
                return [types.TextContent(type="text", text=f"Error: JOB_NOT_FOUND - {job_id}")]
                
            if job.status in [JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.ESCALATED]:
                return [types.TextContent(type="text", text="Error: JOB_ALREADY_DONE - Job déjà terminé, rien à annuler.")]
                
            cancelled = await engine.cancel_job(job_id, arguments.get("reason", ""))
            
            response = CancelTaskResponse(job_id=job_id, status=JobStatus.CANCELLED)
            return [types.TextContent(type="text", text=response.model_dump_json(indent=2))]
            
        else:
            raise ValueError(f"Unknown tool: {name}")
    except Exception as e:
        logger.error(f"Error handling tool {name}: {e}")
        return [types.TextContent(type="text", text=f"Internal Error: {str(e)}")]

async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="chrysalide",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                )
            )
        )
