import os
import re
import yaml
from typing import Dict, List, Any
from pathlib import Path

DEFAULT_ALLOWED = [
    "git *", "python *", "python3 *", "pytest *", 
    "ls *", "cat *", "grep *", "find *", "echo *"
]

DEFAULT_ALLOWED_NETWORK = [
    "pip *", "npm *", "curl *", "wget *"
]

DEFAULT_DENIED = [
    "* rm *", "rm *", "sudo *", "su *", "bash -c*", "sh -c*",
    "*> *", "*>> *", "*| *", "*& *", "*; *"
]

def glob_to_regex(pattern: str) -> re.Pattern:
    """Convert a simple shell glob with * to a regex."""
    # Escape regex special characters, but leave * alone for now
    escaped = ""
    for char in pattern:
        if char in ".*?+[]()|\\^$":
            if char == "*":
                escaped += char
            else:
                escaped += "\\" + char
        else:
            escaped += char
            
    p = escaped
    
    has_space_star = p.endswith(" *")
    if has_space_star:
        p = p[:-2]
        
    p = p.replace("*", ".*")
    
    if has_space_star:
        p = p + "( .*)?"
        
    regex_str = "^" + p + "$"
    return re.compile(regex_str)

class CommandWhitelist:
    def __init__(self, config_path: str = "config/allowed_commands.yaml"):
        self.allowed: List[re.Pattern] = []
        self.allowed_network: List[re.Pattern] = []
        self.always_denied: List[re.Pattern] = []
        self._load_config(config_path)
        
    def _load_config(self, config_path: str):
        path = Path(config_path)
        
        allowed = DEFAULT_ALLOWED
        allowed_net = DEFAULT_ALLOWED_NETWORK
        denied = DEFAULT_DENIED
        
        if path.exists():
            try:
                with open(path, "r") as f:
                    data = yaml.safe_load(f)
                    if data:
                        allowed = data.get("allowed", allowed)
                        allowed_net = data.get("allowed_with_network", allowed_net)
                        denied = data.get("always_denied", denied)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to load {config_path}: {e}. Using defaults.")
                
        self.allowed = [glob_to_regex(p) for p in allowed]
        self.allowed_network = [glob_to_regex(p) for p in allowed_net]
        self.always_denied = [glob_to_regex(p) for p in denied]
        
    def is_allowed(self, command: str, allow_network: bool = False) -> bool:
        command = command.strip()
        
        # 1. Check always_denied
        for pattern in self.always_denied:
            if pattern.match(command):
                return False
                
        # 2. Check allowed
        for pattern in self.allowed:
            if pattern.match(command):
                return True
                
        # 3. Check allowed_with_network
        if allow_network:
            for pattern in self.allowed_network:
                if pattern.match(command):
                    return True
                    
        return False
