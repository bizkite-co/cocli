import os
import sys
from pathlib import Path


def get_cuda_env() -> dict[str, str]:
    """Get the required LD_LIBRARY_PATH updates for NVIDIA libs."""
    venv_path = Path(sys.prefix)

    # Locate nvidia packages
    site_packages = (
        venv_path
        / "lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
    )

    # In some installations, site-packages is just lib/python3.x/site-packages
    # but sometimes it's different.
    lib_path = venv_path / "lib"
    if lib_path.exists():
        for py_dir in lib_path.iterdir():
            if py_dir.is_dir() and "python" in py_dir.name:
                sp = py_dir / "site-packages"
                if sp.exists():
                    site_packages = sp
                    break

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

    existing_ld = os.environ.get("LD_LIBRARY_PATH", "")
    new_ld_path = ":".join(lib_paths + ([existing_ld] if existing_ld else []))

    return {"LD_LIBRARY_PATH": new_ld_path}
