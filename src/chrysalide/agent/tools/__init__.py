from typing import List, Dict, Any
from chrysalide.sandbox import GitWorktreeSandbox
from .fs_tools import get_fs_tools, execute_fs_tool
from .cmd_tools import get_cmd_tools, execute_cmd_tool
from .git_tools import get_git_tools, execute_git_tool

class ToolRegistry:
    def __init__(self, sandbox: GitWorktreeSandbox):
        self.sandbox = sandbox
        self._tools = []
        self._tools.extend(get_fs_tools())
        self._tools.extend(get_cmd_tools())
        self._tools.extend(get_git_tools())
        
    def get_definitions(self) -> List[Dict[str, Any]]:
        return self._tools
        
    async def execute(self, name: str, arguments: Dict[str, Any]) -> str:
        fs_names = [t["name"] for t in get_fs_tools()]
        cmd_names = [t["name"] for t in get_cmd_tools()]
        git_names = [t["name"] for t in get_git_tools()]
        
        if name in fs_names:
            return await execute_fs_tool(name, arguments, self.sandbox)
        elif name in cmd_names:
            return await execute_cmd_tool(name, arguments, self.sandbox)
        elif name in git_names:
            return await execute_git_tool(name, arguments, self.sandbox)
        else:
            return f"Error: Tool {name} not found"
