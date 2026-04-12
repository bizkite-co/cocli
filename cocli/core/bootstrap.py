import os
import sys
from pathlib import Path
from cocli.core import env_setup


def setup_environment() -> None:
    env_updates = {}

    cuda_env = env_setup.get_cuda_env()

    # 1. CUDA setup
    if cuda_env:
        required_paths = cuda_env["LD_LIBRARY_PATH"].split(":")
        current_ld_path = os.environ.get("LD_LIBRARY_PATH", "")

        # Check if ANY of the required paths are missing
        needs_update = False
        for path in required_paths:
            if path and path not in current_ld_path:
                needs_update = True
                break

        if needs_update:
            env_updates.update(cuda_env)

    # 2. Data Home setup
    if "COCLI_DATA_HOME" not in os.environ:
        # Resolve to data folder in project root
        project_root = Path(__file__).parent.parent.parent
        env_updates["COCLI_DATA_HOME"] = str(project_root / "data")

    if env_updates:
        print(f"DEBUG: Re-executing with: {env_updates}")
        os.environ.update(env_updates)
        os.execv(sys.executable, [sys.executable] + sys.argv)
