"""Compact the entity field journal and upload the files that changed.

The journal stays in ``core``. This module is the product step that pushes
the rewritten company or person markdown to the campaign data bucket.
Schedule ``cocli wal compact`` from cron. Do not point it at a data root
you have not meant to publish.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from cocli.core.entity_field_log import compact_entity_field_journal
from cocli.core.paths import paths


def compact_and_upload_entity_fields(
    upload: Optional[Callable[[Path, str], None]] = None,
    *,
    data_root: Optional[Path] = None,
    wal_root: Optional[Path] = None,
    archive: bool = True,
    compactor_id: Optional[str] = None,
) -> tuple[bool, int, int, list[str]]:
    """Fold the journal, then upload each rewritten entity file.

    ``upload`` receives the local path and the S3 key (the path relative to
    the data root, POSIX). ``None`` skips the upload. Returns
    ``(did_work, record_count, entity_count, keys)``.
    """
    root = data_root if data_root is not None else paths.root
    did, n_rec, n_ent, written = compact_entity_field_journal(
        wal_root=wal_root,
        data_root=root,
        archive=archive,
        compactor_id=compactor_id,
    )
    keys: list[str] = []
    if upload is None:
        return did, n_rec, n_ent, keys
    for path in written:
        key = path.relative_to(root).as_posix()
        upload(path, key)
        keys.append(key)
    return did, n_rec, n_ent, keys
