import os
import uuid
import shutil
import asyncio
import logging
from typing import Tuple
from pathlib import Path
import pytest
from unittest.mock import patch, AsyncMock, mock_open

from chrysalide.sandbox import GitWorktreeSandbox, SandboxError

logger = logging.getLogger(__name__)

@pytest.fixture
def sandbox():
    return GitWorktreeSandbox('/fake/repo/path', job_id='testjob')

@pytest.fixture
def mock_subprocess_shell():
    with patch('asyncio.create_subprocess_shell', new_callable=AsyncMock) as mock:
        yield mock

class TestGitWorktreeSandbox:
    @pytest.mark.asyncio
    @patch('pathlib.Path.exists', return_value=True)
    @patch('pathlib.Path.mkdir')
    @patch('builtins.open', new_callable=mock_open, read_data="node_modules/\n")
    async def test_setup_creates_worktree_and_updates_gitignore(self, mock_file, mock_mkdir, mock_exists, sandbox, mock_subprocess_shell):
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b'output', b''))
        mock_subprocess_shell.return_value = mock_proc

        sandbox._ignore_git_check = True
        await sandbox.setup()

        # Check subprocess was called correctly
        mock_subprocess_shell.assert_called_once_with(
            'git worktree add /fake/repo/path/.chrysalide/worktrees/testjob -b chrysalide/testjob',
            cwd='/fake/repo/path',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Check gitignore update (open was called to append)
        mock_file.assert_any_call(Path('/fake/repo/path/.gitignore'), 'a')
        handle = mock_file()
        handle.write.assert_called_with('\n# Chrysalide\n.chrysalide/\n')

    @pytest.mark.asyncio
    async def test_setup_raises_error_on_non_git_repo(self, sandbox):
        with pytest.raises(SandboxError, match="n'est pas la racine d'un dépôt git"):
            await sandbox.setup()

    @pytest.mark.asyncio
    @patch('pathlib.Path.exists', return_value=True)
    @patch('shutil.rmtree')
    async def test_teardown_removes_worktree(self, mock_rmtree, mock_exists, sandbox, mock_subprocess_shell):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b'output', b''))
        mock_subprocess_shell.return_value = mock_proc

        await sandbox.teardown()

        mock_subprocess_shell.assert_called_once_with(
            'git worktree remove -f /fake/repo/path/.chrysalide/worktrees/testjob',
            cwd='/fake/repo/path',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

    @pytest.mark.asyncio
    @patch('os.setsid', create=True)
    async def test_execute_runs_allowed_command(self, mock_setsid, sandbox, mock_subprocess_shell):
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b'command output', b''))
        mock_subprocess_shell.return_value = mock_proc

        returncode, stdout, stderr = await sandbox.execute('ls -la')

        assert returncode == 0
        assert stdout == 'command output'
        assert stderr == ''
        mock_subprocess_shell.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_execute_blocks_denied_command(self, sandbox, mock_subprocess_shell):
        returncode, stdout, stderr = await sandbox.execute('rm -rf /')

        assert returncode == -1
        assert stdout == ''
        assert 'Erreur de sécurité' in stderr
        mock_subprocess_shell.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_blocks_network_if_disabled(self, sandbox, mock_subprocess_shell):
        returncode, stdout, stderr = await sandbox.execute('curl http://example.com')

        assert returncode == -1
        assert 'Erreur de sécurité' in stderr
        mock_subprocess_shell.assert_not_called()
        
    @pytest.mark.asyncio
    async def test_execute_allows_network_if_enabled(self, mock_subprocess_shell):
        net_sandbox = GitWorktreeSandbox('/fake/repo/path', job_id='testjob', allow_network=True)
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b'downloaded', b''))
        mock_subprocess_shell.return_value = mock_proc

        returncode, stdout, stderr = await net_sandbox.execute('curl http://example.com')

        assert returncode == 0
        assert stdout == 'downloaded'
        mock_subprocess_shell.assert_called_once()

    @pytest.mark.asyncio
    @patch('os.setsid', create=True)
    async def test_execute_handles_timeout(self, mock_setsid, sandbox, mock_subprocess_shell):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
        mock_subprocess_shell.return_value = mock_proc

        returncode, stdout, stderr = await sandbox.execute('ls')

        assert returncode == -1
        assert stdout == ''
        assert f"Erreur: Timeout après {sandbox.timeout_sec}s" in stderr

    def test_get_path(self, sandbox):
        assert sandbox.get_path() == Path('/fake/repo/path/.chrysalide/worktrees/testjob')
