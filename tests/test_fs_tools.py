import asyncio
import os
from pathlib import Path
from typing import List, Dict, Any
import pytest
from unittest.mock import MagicMock, patch
from chrysalide.sandbox import GitWorktreeSandbox
from chrysalide.agent.tools.fs_tools import get_fs_tools, execute_fs_tool

class TestGetFsTools:
    def test_get_fs_tools_returns_correct_structure(self):
        tools = get_fs_tools()
        assert isinstance(tools, list)
        assert len(tools) == 3
        assert tools[0]["name"] == "read_file"
        assert tools[1]["name"] == "write_file"
        assert tools[2]["name"] == "list_dir"

class TestExecuteFsTool:
    @pytest.fixture
    def sandbox(self):
        sandbox = MagicMock(spec=GitWorktreeSandbox)
        sandbox.get_path.return_value = Path("/sandbox")
        return sandbox

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self, tmp_path):
        self.test_dir = tmp_path / "sandbox"
        self.test_dir.mkdir()
        yield
        for item in self.test_dir.iterdir():
            if item.is_file():
                item.unlink()
            else:
                for sub_item in item.iterdir():
                    sub_item.unlink()
                item.rmdir()

    def test_execute_fs_tool_read_file_success(self, sandbox):
        test_file = self.test_dir / "test.txt"
        test_file.write_text("Hello, World!")
        sandbox.get_path.return_value = self.test_dir

        result = asyncio.run(execute_fs_tool("read_file", {"path": "test.txt"}, sandbox))
        assert result == "Hello, World!"

    def test_execute_fs_tool_read_file_not_found(self, sandbox):
        sandbox.get_path.return_value = self.test_dir

        result = asyncio.run(execute_fs_tool("read_file", {"path": "nonexistent.txt"}, sandbox))
        assert result == "Erreur: Fichier introuvable"

    def test_execute_fs_tool_read_file_too_large(self, sandbox):
        test_file = self.test_dir / "large.txt"
        test_file.write_bytes(b"a" * (1024 * 1024 + 1))
        sandbox.get_path.return_value = self.test_dir

        result = asyncio.run(execute_fs_tool("read_file", {"path": "large.txt"}, sandbox))
        assert result == "Erreur: Fichier trop grand (>1Mo)"

    def test_execute_fs_tool_write_file_success(self, sandbox):
        sandbox.get_path.return_value = self.test_dir

        result = asyncio.run(execute_fs_tool("write_file", {"path": "test.txt", "content": "Hello, World!"}, sandbox))
        assert result == "Fichier test.txt écrit avec succès."
        assert (self.test_dir / "test.txt").read_text() == "Hello, World!"

    def test_execute_fs_tool_list_dir_success(self, sandbox):
        (self.test_dir / "file1.txt").write_text("File 1")
        (self.test_dir / "file2.txt").write_text("File 2")
        sandbox.get_path.return_value = self.test_dir

        result = asyncio.run(execute_fs_tool("list_dir", {"path": "."}, sandbox))
        assert "file1.txt" in result
        assert "file2.txt" in result

    def test_execute_fs_tool_list_dir_empty(self, sandbox):
        sandbox.get_path.return_value = self.test_dir

        result = asyncio.run(execute_fs_tool("list_dir", {"path": "."}, sandbox))
        assert result == "(répertoire vide)"

    def test_execute_fs_tool_invalid_tool_name(self, sandbox):
        sandbox.get_path.return_value = self.test_dir

        result = asyncio.run(execute_fs_tool("invalid_tool", {"path": "test.txt"}, sandbox))
        assert result == "Outil non géré: invalid_tool"

    def test_execute_fs_tool_invalid_path(self, sandbox):
        sandbox.get_path.return_value = self.test_dir

        result = asyncio.run(execute_fs_tool("read_file", {"path": "../outside.txt"}, sandbox))
        assert result == "Erreur: Chemin invalide (.. interdit)"

    def test_execute_fs_tool_access_outside_sandbox(self, sandbox):
        sandbox.get_path.return_value = self.test_dir

        result = asyncio.run(execute_fs_tool("read_file", {"path": "/etc/passwd"}, sandbox))
        assert result == "Erreur: Accès en dehors de la sandbox interdit"

    def test_execute_fs_tool_list_dir_not_found(self, sandbox):
        sandbox.get_path.return_value = self.test_dir

        result = asyncio.run(execute_fs_tool("list_dir", {"path": "nonexistent_dir"}, sandbox))
        assert result == "Erreur: Répertoire introuvable"