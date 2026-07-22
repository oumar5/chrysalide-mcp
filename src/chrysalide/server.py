import os
import asyncio
import logging
from typing import Dict, Any

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types

from chrysalide.models import JobConfig
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
            name="start_job",
            description="Démarre une tâche asynchrone (job) de modification de code.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Chemin absolu vers le dépôt git à modifier"
                    },
                    "goal": {
                        "type": "string",
                        "description": "Objectif de la tâche à accomplir"
                    }
                },
                "required": ["repo_path", "goal"]
            }
        ),
        types.Tool(
            name="check_job",
            description="Vérifie l'état et le résultat d'une tâche asynchrone.",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "L'identifiant du job retourné par start_job"
                    }
                },
                "required": ["job_id"]
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "start_job":
        repo_path = arguments.get("repo_path")
        goal = arguments.get("goal")
        
        if not repo_path or not goal:
            return [types.TextContent(type="text", text="Error: repo_path and goal are required.")]
            
        req = JobConfig(repo_path=repo_path, goal=goal)
        job_id = await engine.start_job(req)
        
        return [types.TextContent(type="text", text=f"Job started. ID: {job_id}")]
        
    elif name == "check_job":
        job_id = arguments.get("job_id")
        if not job_id:
            return [types.TextContent(type="text", text="Error: job_id is required.")]
            
        status = await store.get_job(job_id)
        if not status:
            return [types.TextContent(type="text", text=f"Error: Job {job_id} not found.")]
            
        return [types.TextContent(type="text", text=status.model_dump_json(indent=2))]
        
    raise ValueError(f"Unknown tool: {name}")

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
