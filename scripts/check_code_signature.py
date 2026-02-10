#!/usr/bin/env python3
import hashlib
from pathlib import Path

# Directories to include in the signature
INCLUDES = ["cocli", "scripts", "tests", "features", "Makefile", "pyproject.toml"]
# Patterns to ignore
EXCLUDES = ["__pycache__", ".pyc", ".pyo", ".git", "data", "recovery", ".logs"]

def get_code_signature() -> str:
    hasher = hashlib.md5()
    root = Path(".")
    
    # Collect all files to hash
    files_to_hash = []
    for include in INCLUDES:
        path = root / include
        if path.is_file():
            files_to_hash.append(path)
        elif path.is_dir():
            for f in path.rglob("*"):
                if f.is_file() and not any(ex in str(f) for ex in EXCLUDES):
                    files_to_hash.append(f)
                    
    # Sort for determinism
    files_to_hash.sort()
    
    # Hash each file
    for f in files_to_hash:
        try:
            hasher.update(f.read_bytes())
        except (PermissionError, FileNotFoundError):
            continue
            
    return hasher.hexdigest()

if __name__ == "__main__":
    import sys
    sig = get_code_signature()
    
    sig_file = Path(".code_signature.md5")
    
    if "--check" in sys.argv:
        if sig_file.exists() and sig_file.read_text().strip() == sig:
            # Match found
            sys.exit(0)
        else:
            # No match
            sys.exit(1)
    
    if "--update" in sys.argv:
        sig_file.parent.mkdir(parents=True, exist_ok=True)
        sig_file.write_text(sig)
        print(f"Code signature updated: {sig}")
    else:
        print(sig)
