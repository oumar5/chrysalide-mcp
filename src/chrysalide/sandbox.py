import os
import uuid
import shutil
import asyncio
import logging
from typing import Tuple
from pathlib import Path
from chrysalide.security.config import CommandWhitelist

logger = logging.getLogger(__name__)

class SandboxError(Exception):
    pass

class GitWorktreeSandbox:
    """
    Context manager qui crée un git worktree temporaire pour isoler les modifications de l'agent.
    Détruit le worktree à la fin de la session (sauf si persist=True).
    """
    def __init__(self, original_repo_path: str, job_id: str = None, timeout_sec: int = 60, persist: bool = True, allow_network: bool = False):
        self.original_repo_path = Path(original_repo_path).resolve()
        self.timeout_sec = timeout_sec
        self.persist = persist
        self.allow_network = allow_network
        
        self.job_id = job_id or f"chrys_{uuid.uuid4().hex[:12]}"
        self.branch_name = f"chrysalide/{self.job_id}"
        
        # Le worktree sera créé dans .chrysalide/worktrees/<job_id>
        self.chrysalide_dir = self.original_repo_path / ".chrysalide"
        self.worktree_path = self.chrysalide_dir / "worktrees" / self.job_id
        
        # Instanciation de la whitelist
        self.whitelist = CommandWhitelist()
        
    async def __aenter__(self) -> "GitWorktreeSandbox":
        await self.setup()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if not self.persist:
            await self.teardown()
            
    async def setup(self):
        # Vérifier que c'est un dépôt git
        if not (self.original_repo_path / ".git").exists() and not (self.original_repo_path / ".git").is_file():
             if not hasattr(self, '_ignore_git_check'): # hack pour tests
                 raise SandboxError(f"Le chemin {self.original_repo_path} n'est pas la racine d'un dépôt git.")
            
        # Créer le répertoire .chrysalide s'il n'existe pas
        self.chrysalide_dir.mkdir(parents=True, exist_ok=True)
        
        # Ajouter .chrysalide au .gitignore si nécessaire
        gitignore_path = self.original_repo_path / ".gitignore"
        gitignore_content = ""
        if gitignore_path.exists():
            with open(gitignore_path, "r") as f:
                gitignore_content = f.read()
                
        if ".chrysalide" not in gitignore_content and ".chrysalide/" not in gitignore_content:
            with open(gitignore_path, "a") as f:
                f.write("\n# Chrysalide\n.chrysalide/\n")
                
        # Créer le dossier parent du worktree au cas où
        self.worktree_path.parent.mkdir(parents=True, exist_ok=True)
            
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
            
            if self.worktree_path.exists():
                shutil.rmtree(self.worktree_path, ignore_errors=True)
                
            logger.info(f"Sandbox {self.worktree_path} détruite.")

    async def execute(self, command: str) -> Tuple[int, str, str]:
        """Exécute une commande shell dans le worktree avec timeout et vérification de sécurité."""
        if not self.whitelist.is_allowed(command, self.allow_network):
            logger.warning(f"Commande rejetée par la whitelist: {command}")
            return -1, "", f"Erreur de sécurité: Commande non autorisée ('{command}')."
            
        # Environnement restreint
        restricted_env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", "/tmp"),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8")
        }
            
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=str(self.worktree_path),
                env=restricted_env,
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
