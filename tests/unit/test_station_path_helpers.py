"""Pilot for PhaseRef + station path helpers (0010)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from cocli.core.paths import paths
from cocli.station_defs.campaigns.indexes.emails import EMAIL_INBOX
from cocli.station_defs.campaigns.queues import DFQ_QUEUE_STATION
from cocli.station_defs.path_helpers import (
    email_inbox_item_path,
    email_inbox_phases,
    queue_pending_item_path,
    queue_pending_relative,
)
from stations.segments import collect_phases, collect_shard


def test_email_inbox_phase_ref_not_magic_string() -> None:
    ph = email_inbox_phases()
    assert ph.inbox.name == "inbox"
    assert ph.is_phase(ph.inbox)


def test_email_inbox_item_path(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(paths, "root", tmp_path)
    p = email_inbox_item_path("camp", "a@example.com")
    sh = collect_shard(EMAIL_INBOX.segments)
    assert sh is not None
    expected_shard = sh.shard_for("a@example.com")
    assert p == (
        tmp_path
        / "campaigns"
        / "camp"
        / "indexes"
        / "emails"
        / "inbox"
        / expected_shard
        / "a@example.com"
    )


def test_queue_pending_uses_declared_pending_token(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(paths, "root", tmp_path)
    ph = collect_phases(DFQ_QUEUE_STATION.segments)
    assert ph is not None
    p = queue_pending_item_path("camp", "enrichment", "task99", phase=ph.pending)
    assert "pending" in p.parts
    assert p.name == "task99"
    rel = queue_pending_relative("task99", phase=ph.pending)
    assert rel.startswith("pending/")
    assert rel.endswith("/task99")


def test_queue_rejects_unknown_phase(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(paths, "root", tmp_path)
    with pytest.raises(ValueError, match="not in declared"):
        queue_pending_item_path("camp", "enrichment", "t1", phase="not-a-phase")
