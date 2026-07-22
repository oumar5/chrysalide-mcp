from typing import List, Dict, Any
from chrysalide.sandbox import GitWorktreeSandbox

def get_git_tools() -> List[Dict[str, Any]]:
    return [
        {
            "name": "git_status",
            "description": "Affiche l'état des fichiers modifiés (git status -s)",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        {
            "name": "git_diff",
            "description": "Affiche les différences depuis le dernier commit.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        {
            "name": "git_commit",
            "description": "Ajoute tous les fichiers et crée un commit.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Message du commit"}
                },
                "required": ["message"]
            }
        }
    ]

async def execute_git_tool(name: str, arguments: Dict[str, Any], sandbox: GitWorktreeSandbox) -> str:
    if name == "git_status":
        code, out, err = await sandbox.execute("git status -s")
        return out if out else "Aucune modification (clean)"
        
    elif name == "git_diff":
        code, out, err = await sandbox.execute("git diff")
        return out if out else "Aucune différence"
        
    elif name == "git_commit":
        msg = arguments.get("message", "Changement généré par Chrysalide")
        await sandbox.execute("git add .")
        msg_escaped = msg.replace('"', '\\"')
        code, out, err = await sandbox.execute(f'git commit -m "{msg_escaped}"')
        return f"Exit code: {code}\nSTDOUT:\n{out}\nSTDERR:\n{err}"
        
    return f"Outil non géré: {name}"
