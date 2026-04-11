import os
import sys
from pathlib import Path
from typing import Dict


def get_cuda_env() -> Dict[str, str]:
    """Get the required LD_LIBRARY_PATH updates for NVIDIA libs."""
    venv_path = Path(sys.prefix)

    # Locate nvidia packages
    site_packages = (
        venv_path
        / "lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
    )

    if not site_packages.exists():
        return {}

    nvidia_path = site_packages / "nvidia"
    if not nvidia_path.exists():
        return {}

    nvidia_lib_paths = [
        nvidia_path / "cublas" / "lib",
        nvidia_path / "cudnn" / "lib",
        nvidia_path / "cuda_nvrtc" / "lib",
    ]

    # Filter only those that exist
    lib_paths = [str(p) for p in nvidia_lib_paths if p.exists()]

    if not lib_paths:
        return {}

    new_ld_path = ":".join(
        lib_paths
        + (
            [os.environ.get("LD_LIBRARY_PATH", "")]
            if os.environ.get("LD_LIBRARY_PATH")
            else []
        )
    )

    return {"LD_LIBRARY_PATH": new_ld_path}
