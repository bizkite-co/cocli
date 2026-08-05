"""Backup file naming policy.

Every ``.bak`` this codebase writes must carry a timestamp - an unstamped
``foo.bak`` gets silently overwritten by the next run, which is exactly what
almost destroyed the one forensic artifact from gm_list_to_checkpoint.py's
June 29 compaction run before anyone noticed.
"""

from datetime import datetime, timezone
from pathlib import Path


def timestamped_backup_path(path: Path) -> Path:
    """Returns ``<path>.<UTC timestamp>.bak`` - never ``<path>.bak`` alone.

    Colon-free, sortable format (``%Y%m%dT%H%M%SZ``) so ``ls`` orders
    backups chronologically and the name stays safe on every filesystem
    this project touches (including exFAT/Windows via WSL).
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return path.parent / f"{path.name}.{stamp}.bak"
