import os
import uuid
import shutil
import asyncio
import logging
from typing import Tuple
from pathlib import Path
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

logger = logging.getLogger(__name__)

class SandboxError(Exception):
    pass

class GitWorktreeSandbox:
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
        if not (self.original_repo_path / ".git").exists() and not (self.original_repo_path / ".git").is_file():
             if not hasattr(self, '_ignore_git_check'):
                 raise SandboxError(f"Le chemin {self.original_repo_path} n'est pas la racine d'un dépôt git.")
            
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
        try:
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

@pytest.fixture
def sandbox():
    with patch('uuid.uuid4', return_value=uuid.UUID('12345678123456781234567812345678')):
        return GitWorktreeSandbox('/fake/repo/path')

@pytest.fixture
def mock_subprocess_shell():
    with patch('asyncio.create_subprocess_shell', new_callable=AsyncMock) as mock:
        yield mock

class TestGitWorktreeSandbox:
    @pytest.mark.asyncio
    async def test_setup_creates_worktree(self, sandbox, mock_subprocess_shell):
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b'output', b''))
        mock_subprocess_shell.return_value = mock_proc

        sandbox._ignore_git_check = True
        await sandbox.setup()

        mock_subprocess_shell.assert_called_once_with(
            'git worktree add /tmp/chrysalide-wk-12345678 -b chrysalide-task-12345678',
            cwd='/fake/repo/path',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

    @pytest.mark.asyncio
    async def test_setup_raises_error_on_non_git_repo(self, sandbox):
        with pytest.raises(SandboxError, match="n'est pas la racine d'un dépôt git"):
            await sandbox.setup()

    @pytest.mark.asyncio
    async def test_teardown_removes_worktree(self, sandbox, mock_subprocess_shell):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b'output', b''))
        mock_subprocess_shell.return_value = mock_proc

        sandbox.worktree_path.mkdir(parents=True, exist_ok=True)
        await sandbox.teardown()

        mock_subprocess_shell.assert_called_once_with(
            'git worktree remove -f /tmp/chrysalide-wk-12345678',
            cwd='/fake/repo/path',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

    @pytest.mark.asyncio
    async def test_execute_runs_command(self, sandbox, mock_subprocess_shell):
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b'command output', b''))
        mock_subprocess_shell.return_value = mock_proc

        sandbox.worktree_path.mkdir(parents=True, exist_ok=True)
        returncode, stdout, stderr = await sandbox.execute('ls')

        assert returncode == 0
        assert stdout == 'command output'
        assert stderr == ''

    @pytest.mark.asyncio
    async def test_execute_handles_timeout(self, sandbox, mock_subprocess_shell):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
        mock_subprocess_shell.return_value = mock_proc

        sandbox.worktree_path.mkdir(parents=True, exist_ok=True)
        returncode, stdout, stderr = await sandbox.execute('sleep 10')

        assert returncode == -1
        assert stdout == ''
        assert stderr == f"Erreur: Timeout après {sandbox.timeout_sec}s"

    @pytest.mark.asyncio
    async def test_execute_handles_exception(self, sandbox, mock_subprocess_shell):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=Exception('unexpected error'))
        mock_subprocess_shell.return_value = mock_proc

        sandbox.worktree_path.mkdir(parents=True, exist_ok=True)
        returncode, stdout, stderr = await sandbox.execute('ls')

        assert returncode == -1
        assert stdout == ''
        assert 'Erreur système: unexpected error' in stderr

    def test_get_path(self, sandbox):
        assert sandbox.get_path() == Path('/tmp/chrysalide-wk-12345678')