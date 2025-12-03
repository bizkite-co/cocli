#!/usr/bin/env python3
import sys
from pathlib import Path

def increment_version() -> str:
    version_file = Path("VERSION")
    if not version_file.exists():
        version = "0.0.1"
        version_file.write_text(version)
        print(version)
        return version

    version = version_file.read_text().strip()
    try:
        major, minor, patch = map(int, version.split('.'))
        new_version = f"{major}.{minor}.{patch + 1}"
        version_file.write_text(new_version)
        print(new_version)
        return new_version
    except ValueError:
        print(f"Error: Invalid version format '{version}'. expected major.minor.patch", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    increment_version()
