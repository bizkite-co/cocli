import os
import sys
from pathlib import Path
from cocli.core import env_setup


def setup_environment() -> None:
    env_updates = {}

    # 1. CUDA setup
    cuda_env = env_setup.get_cuda_env()
    if cuda_env:
        required_path = cuda_env["LD_LIBRARY_PATH"].split(":")[0]
        current_ld_path = os.environ.get("LD_LIBRARY_PATH", "")
        if required_path not in current_ld_path:
            env_updates.update(cuda_env)

    # 2. Data Home setup
    if "COCLI_DATA_HOME" not in os.environ:
        # Resolve to data folder in project root
        project_root = Path(__file__).parent.parent.parent
        env_updates["COCLI_DATA_HOME"] = str(project_root / "data")

    if env_updates:
        os.environ.update(env_updates)
        os.execv(sys.executable, [sys.executable] + sys.argv)
