"""Entity field-update journal (stations-shaped log of patch facts).

This module is **not** dead husk and is **not** "out of stations." It is cocli's
product instance of concurrent field-level updates as append-only log records.

## Why it exists

Two writers often update the *same entity* for different reasons — e.g. one sets
``phone``, another sets ``address``. Whole-file overwrite of ``_index.md`` loses
the other field. The protocol is:

1. **Append** an immutable field-update fact (target + field + value + timestamp).
2. **Read/fold** facts onto the entity base (LWW per field).
3. **Compact** folds the journal and writes whole entity snapshots
   (:func:`cocli.core.entity_field_log.compact_entity_field_journal`).

That is the stations trichotomy (log → fold → present state), with payload kind
= field-update. Canonical example and rules:
``stations/decisions/0009-field-update-records-as-log-facts.md``.

## Stations wiring

``append_update`` / ``read_updates`` go through
:class:`cocli.core.entity_field_log.EntityFieldLogEdge` (implements stations
``LogEdge``). On-disk Shape A segments (``{date}_{node}.usv``) are unchanged.

## Layout

- Journal segments: ``paths.wal_journal(node_id)`` — Shape A, append-only.
- Entity identity: ``paths.wal_target_id(target_dir)`` (e.g. companies/slug).
- Apply on load: ``Company.from_directory`` and ``Person.from_file`` call
  :func:`read_updates`.
- Compact: :func:`cocli.core.entity_field_log.compact_entity_field_journal`.

## Further docs

- stations decision **0009** (normative): field-update records as log facts
- stations GLOSSARY trichotomy + Transform note pointing at 0009
- stations consumers/cocli.md
- cocli ``docs/data-management/distributed-update-propagation.md``
- cocli ``docs/wal-strategy.md`` (campaign **index** WAL — different instance)
"""

from __future__ import annotations

import json
import logging
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from cocli.core.entity_field_log import open_entity_field_log
from cocli.core.paths import paths
from cocli.models.wal.record import DatagramRecord

logger = logging.getLogger(__name__)


def get_node_id() -> str:
    return socket.gethostname()


def append_update(
    target_dir: Path,
    field: str,
    value: Any,
    campaign_name: Optional[str] = None,
) -> None:
    """Append one field-update fact via stations LogEdge (decision 0009).

    The record is a whole typed log entry, not an in-place edit of the entity file.
    """
    from cocli.core.config import get_campaign
    from cocli.core.environment import get_environment

    node_id = get_node_id()
    target_id = paths.wal_target_id(target_dir)
    effective_campaign = campaign_name or get_campaign() or "unknown"

    if isinstance(value, (list, dict)):
        import json

        value_str = json.dumps(value)
    else:
        value_str = str(value)

    record = DatagramRecord(
        timestamp=datetime.now(UTC).isoformat(),
        node_id=node_id,
        campaign_name=effective_campaign,
        environment=get_environment().value,
        target=target_id,
        field=field,
        value=value_str,
    )
    open_entity_field_log().append(record)


def canonical_field_value(value: Any) -> str:
    """Stable text for comparing a file value with a model dump."""
    if value is None:
        return ""
    if isinstance(value, list):
        if all(not isinstance(item, (list, dict)) for item in value):
            return json.dumps(sorted(str(item) for item in value))
        return json.dumps(value, sort_keys=True, default=str)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, default=str)
    return str(value)


def _is_blank(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def journal_field_changes(
    target_dir: Path,
    previous: dict[str, Any],
    current: dict[str, Any],
    *,
    campaign_name: Optional[str] = None,
) -> list[str]:
    """Append one datagram per field that changed. Returns those field names.

    A missing value and an empty list or dict are the same, so the first
    WAL-aware save of an older file does not emit a row for every default.
    ``slug`` is the entity identity and is never journaled.
    """
    changed: list[str] = []
    fields = set(previous) | set(current)
    fields.discard("slug")
    for field in sorted(fields):
        old = previous.get(field)
        new = current.get(field)
        if _is_blank(old) and _is_blank(new):
            continue
        if canonical_field_value(old) == canonical_field_value(new):
            continue
        append_update(target_dir, field, "" if new is None else new, campaign_name=campaign_name)
        changed.append(field)
    return changed


def read_updates(target_dir: Path) -> list[DatagramRecord]:
    """Load field-update facts for one entity via stations LogEdge.

    Callers fold onto base entity state (e.g. ``Company.from_directory``).
    """
    target_id = paths.wal_target_id(target_dir)
    edge = open_entity_field_log()
    records = [r for r in edge.iter_beyond() if r.target == target_id]
    records.sort(key=lambda x: x.timestamp)
    return records
