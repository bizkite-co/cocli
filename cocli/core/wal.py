"""Entity field-update journal (stations-shaped log of patch facts).

This module is **not** dead husk and is **not** "out of stations." It is cocli's
product instance of concurrent field-level updates as append-only log records.

## Why it exists

Two writers often update the *same entity* for different reasons — e.g. one sets
``phone``, another sets ``address``. Whole-file overwrite of ``_index.md`` loses
the other field. The protocol is:

1. **Append** an immutable field-update fact (target + field + value + timestamp).
2. **Read/fold** facts onto the entity base (LWW per field on load today).
3. **Later:** compact into a whole present snapshot and retire journal segments.

That is the stations trichotomy (log → fold → index/entity present state), with
payload kind = field-update. Canonical example and rules:
`stations/decisions/0009-field-update-records-as-log-facts.md`.

## What this is / is not

| This journal | Campaign index WAL (prospects, emails, …) |
| :--- | :--- |
| Field patches → company (etc.) entity state | Whole domain rows → index CURRENT/checkpoint |
| ``paths.wal`` / ``DatagramRecord`` | ``indexes/.../wal`` or ``inbox/`` |
| Stations-shaped; **wiring to LogEdge/Compactor is a follow-on** | Active strangler cutover surface |

Transforms still do **not** in-place patch living files (GLOSSARY § Transform).
Patches are whole *log records*; the folded entity is a whole *present* record.

## Layout

- Journal segments: ``paths.wal_journal(node_id)`` — Shape A style
  (period + writer id), append-only.
- Entity identity: ``paths.wal_target_id(target_dir)`` (e.g. companies/slug).
- Apply path today: ``Company.from_directory`` calls :func:`read_updates` and
  merges fields over YAML frontmatter.

## Further docs

- stations decision **0009** (normative): field-update records as log facts
- stations [GLOSSARY](https://github.com/bizkite-co/stations/blob/main/GLOSSARY.md)
  trichotomy + Transform note pointing at 0009
- stations [consumers/cocli.md](https://github.com/bizkite-co/stations/blob/main/consumers/cocli.md)
- cocli ``docs/data-management/distributed-update-propagation.md`` (gossip + journal)
- cocli ``docs/wal-strategy.md`` (campaign **index** WAL — different instance)

## Implement follow-on

Cut over this journal through ``stations`` ``LogEdge`` + fold/compactor for entity
snapshots (see task-agent:
``implement-stations-logedge-cutover-for-cocli-entity-field-journal-wal.py``).
Until then: document-and-keep; do not delete as Phase-4 husk.
"""

from __future__ import annotations

import logging
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, List, Optional

from ..models.wal.record import RS, DatagramRecord
from .paths import paths

logger = logging.getLogger(__name__)


def get_node_id() -> str:
    return socket.gethostname()


def append_update(
    target_dir: Path,
    field: str,
    value: Any,
    campaign_name: Optional[str] = None,
) -> None:
    """Append one field-update fact to the centralized entity journal.

    The record is a whole typed log entry (stations decision 0009), not an
    in-place edit of the entity file.
    """
    from .config import get_campaign

    node_id = get_node_id()
    wal_file = paths.wal_journal(node_id)
    target_id = paths.wal_target_id(target_dir)

    # Infer campaign if not provided
    effective_campaign = campaign_name or get_campaign() or "unknown"

    # Convert value to string representation (JSON if complex)
    if isinstance(value, (list, dict)):
        import json

        value_str = json.dumps(value)
    else:
        value_str = str(value)

    from .environment import get_environment

    record = DatagramRecord(
        timestamp=datetime.now(UTC).isoformat(),
        node_id=node_id,
        campaign_name=effective_campaign,
        environment=get_environment().value,
        target=target_id,
        field=field,
        value=value_str,
    )

    # Ensure WAL directory exists
    wal_file.parent.mkdir(parents=True, exist_ok=True)

    with open(wal_file, "a") as f:
        f.write(record.to_usv())

    logger.info(f"WAL append: {field}={value_str} in {wal_file}")


def read_updates(target_dir: Path) -> List[DatagramRecord]:
    """Load all field-update facts for one entity from the centralized journal.

    Callers fold onto base entity state (LWW by timestamp per field is the
    current naive policy in ``Company.from_directory``).
    """
    wal_dir = paths.wal
    records: List[DatagramRecord] = []
    if not wal_dir.exists():
        return records

    target_id = paths.wal_target_id(target_dir)

    for wal_file in sorted(wal_dir.glob("*.usv")):
        try:
            content = wal_file.read_text()
            for raw_record in content.split(RS):
                if raw_record.strip():
                    record = DatagramRecord.from_usv(raw_record)
                    if record.target == target_id:
                        records.append(record)
        except Exception as e:
            logger.error(f"Error reading WAL file {wal_file}: {e}")

    # Sort by timestamp (naive 'latest wins' for now)
    records.sort(key=lambda x: x.timestamp)
    return records
