import os
import subprocess
import functools
from enum import Enum
from typing import Optional

class Environment(str, Enum):
    DEV = "dev"
    PROD = "prod"
    UAT = "uat"
    TEST = "test"

@functools.lru_cache(maxsize=1)
def _get_git_branch() -> Optional[str]:
    """
    Detects the current git branch. 
    Cached to avoid repeated subprocess calls.
    """
    try:
        # Basic check: is there a .git folder in the current or parent directory?
        if not os.path.exists(".git") and not os.path.exists("../.git"):
            return None

        return subprocess.check_output(
            ["git", "branch", "--show-current"], 
            stderr=subprocess.STDOUT, 
            text=True,
            timeout=1
        ).strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None
    except Exception:
        return None

def get_environment() -> Environment:
    """
    Returns the current active environment.
    Priority:
    1. COCLI_ENV environment variable.
    2. Git branch auto-detection (dev branch -> DEV env).
    3. Defaults to PROD.
    """
    env_override = os.environ.get("COCLI_ENV")
    if env_override:
        env_str = env_override.lower()
        try:
            return Environment(env_str)
        except ValueError:
            if "test" in env_str:
                return Environment.TEST
            return Environment.PROD
            
    # Auto-detect from git branch if not explicitly overridden
    branch = _get_git_branch()
    if branch == "dev":
        return Environment.DEV
        
    return Environment.PROD

def is_prod() -> bool:
    return get_environment() == Environment.PROD

def is_dev() -> bool:
    return get_environment() == Environment.DEV

def is_test() -> bool:
    return get_environment() == Environment.TEST
