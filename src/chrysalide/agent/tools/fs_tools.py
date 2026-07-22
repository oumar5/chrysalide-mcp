import os
from pathlib import Path
from typing import List, Dict, Any
from chrysalide.sandbox import GitWorktreeSandbox

def get_fs_tools() -> List[Dict[str, Any]]:
    return [
        {
            "name": "read_file",
            "description": "Lit le contenu d'un fichier (max 1Mo).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Chemin relatif du fichier"}
                },
                "required": ["path"]
            }
        },
        {
            "name": "write_file",
            "description": "Écrit du contenu dans un fichier.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Chemin relatif du fichier"},
                    "content": {"type": "string", "description": "Nouveau contenu"}
                },
                "required": ["path", "content"]
            }
        },
        {
            "name": "list_dir",
            "description": "Liste le contenu d'un répertoire.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Chemin relatif du répertoire"}
                },
                "required": ["path"]
            }
        }
    ]

async def execute_fs_tool(name: str, arguments: Dict[str, Any], sandbox: GitWorktreeSandbox) -> str:
    rel_path = arguments.get("path", "")
    if ".." in rel_path:
        return "Erreur: Chemin invalide (.. interdit)"
        
    sandbox_path = sandbox.get_path().resolve()
    target_path = (sandbox.get_path() / rel_path).resolve()
    
    try:
        target_path.relative_to(sandbox_path)
    except ValueError:
        return "Erreur: Accès en dehors de la sandbox interdit"

    if name == "read_file":
        if not target_path.exists():
            return "Erreur: Fichier introuvable"
        if target_path.stat().st_size > 1024 * 1024:
            return "Erreur: Fichier trop grand (>1Mo)"
        return target_path.read_text(errors="replace")
        
    elif name == "write_file":
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(arguments.get("content", ""))
        return f"Fichier {rel_path} écrit avec succès."
        
    elif name == "list_dir":
        if not target_path.exists() or not target_path.is_dir():
            return "Erreur: Répertoire introuvable"
        items = os.listdir(target_path)
        return "\n".join(items) if items else "(répertoire vide)"
        
    return f"Outil non géré: {name}"
