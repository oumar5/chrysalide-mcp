from typing import List, Dict, Any
from chrysalide.sandbox import GitWorktreeSandbox

def get_cmd_tools() -> List[Dict[str, Any]]:
    return [
        {
            "name": "execute_command",
            "description": "Exécute une commande shell (timeout max 60s). Ne lance pas de commande interactive ou de serveur.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "La commande à exécuter"}
                },
                "required": ["command"]
            }
        }
    ]

async def execute_cmd_tool(name: str, arguments: Dict[str, Any], sandbox: GitWorktreeSandbox) -> str:
    if name == "execute_command":
        cmd = arguments.get("command", "")
        code, out, err = await sandbox.execute(cmd)
        result = f"Exit code: {code}\n"
        if out:
            result += f"STDOUT:\n{out}\n"
        if err:
            result += f"STDERR:\n{err}\n"
        return result
    return f"Outil non géré: {name}"
