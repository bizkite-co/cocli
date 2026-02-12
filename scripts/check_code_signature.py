#!/usr/bin/env python3
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, cast

# Directories to include in the signature
INCLUDES = ["cocli", "scripts", "tests", "features", "Makefile", "pyproject.toml"]
# Patterns to ignore
EXCLUDES = ["__pycache__", ".pyc", ".pyo", ".git", "data", "recovery", ".logs"]

SIGNATURES_FILE = Path(".code_signatures.json")

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

def load_signatures() -> Dict[str, str]:
    if not SIGNATURES_FILE.exists():
        return {}
    try:
        data = json.loads(SIGNATURES_FILE.read_text())
        if isinstance(data, dict):
            return cast(Dict[str, str], data)
        return {}
    except json.JSONDecodeError:
        return {}

def save_signatures(signatures: Dict[str, str]) -> None:
    SIGNATURES_FILE.write_text(json.dumps(signatures, indent=2))

if __name__ == "__main__":
    task = "default"
    for i, arg in enumerate(sys.argv):
        if arg == "--task" and i + 1 < len(sys.argv):
            task = sys.argv[i+1]
            break
            
    current_sig = get_code_signature()
    signatures = load_signatures()
    
    if "--check" in sys.argv:
        if signatures.get(task) == current_sig:
            # Match found
            sys.exit(0)
        else:
            # No match
            sys.exit(1)
    
    if "--update" in sys.argv:
        signatures[task] = current_sig
        save_signatures(signatures)
        print(f"Code signature updated for task '{task}': {current_sig}")
    else:
        print(current_sig)
