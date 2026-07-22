import os
import uuid
import shutil
import asyncio
import logging
from typing import Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

class SandboxError(Exception):
    pass

class GitWorktreeSandbox:
    """
    Context manager qui crée un git worktree temporaire pour isoler les modifications de l'agent.
    Détruit le worktree à la fin de la session (sauf si persist=True).
    """
    def __init__(self, original_repo_path: str, timeout_sec: int = 60, persist: bool = False):
        self.original_repo_path = Path(original_repo_path).resolve()
        self.timeout_sec = timeout_sec
        self.persist = persist
        self.worktree_id = str(uuid.uuid4())[:8]
        self.branch_name = f"chrysalide-task-{self.worktree_id}"
        self.worktree_path = Path(f"/tmp/chrysalide-wk-{self.worktree_id}")
        
    async def __aenter__(self) -> "GitWorktreeSandbox":
        await self.setup()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if not self.persist:
            await self.teardown()
            
    async def setup(self):
        # Vérifier que c'est un dépôt git
        if not (self.original_repo_path / ".git").exists() and not (self.original_repo_path / ".git").is_file():
             # Ça peut être un sub-worktree (donc .git est un fichier) ou un repo standard (.git est un dossier)
             if not hasattr(self, '_ignore_git_check'): # hack pour tests
                 raise SandboxError(f"Le chemin {self.original_repo_path} n'est pas la racine d'un dépôt git.")
            
        # Créer le worktree
        cmd = f"git worktree add {self.worktree_path} -b {self.branch_name}"
        
        proc = await asyncio.create_subprocess_shell(
            cmd,
            cwd=str(self.original_repo_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise SandboxError(f"Échec de création du worktree: {stderr.decode()}")
            
        logger.info(f"Sandbox créée dans {self.worktree_path} sur la branche {self.branch_name}")

    async def teardown(self):
        if self.worktree_path.exists():
            cmd = f"git worktree remove -f {self.worktree_path}"
            proc = await asyncio.create_subprocess_shell(
                cmd,
                cwd=str(self.original_repo_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            
            # Forcer la suppression si git worktree remove a échoué
            if self.worktree_path.exists():
                shutil.rmtree(self.worktree_path, ignore_errors=True)
                
            # Optionnel: supprimer la branche créée ? 
            # On la garde pour que l'utilisateur puisse vérifier le travail, 
            # mais on a supprimé le worktree.
            logger.info(f"Sandbox {self.worktree_path} détruite.")

    async def execute(self, command: str) -> Tuple[int, str, str]:
        """Exécute une commande shell dans le worktree avec timeout."""
        try:
            # os.setsid pour créer un process group et pouvoir kill l'arbre entier si besoin
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=str(self.worktree_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                preexec_fn=os.setsid if os.name == 'posix' else None
            )
            
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout_sec)
            return proc.returncode, stdout.decode(errors="replace"), stderr.decode(errors="replace")
            
        except asyncio.TimeoutError:
            if proc.returncode is None:
                if os.name == 'posix':
                    import signal
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                else:
                    proc.kill()
            return -1, "", f"Erreur: Timeout après {self.timeout_sec}s"
        except Exception as e:
            return -1, "", f"Erreur système: {str(e)}"
            
    def get_path(self) -> Path:
        return self.worktree_path
