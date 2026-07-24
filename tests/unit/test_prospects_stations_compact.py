"""Prospects index: stations CURRENT commit + prospects.usv materialization."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cocli.core.stations_runtime import compact_prospects_local


def _usv_line(place_id: str, name: str, updated_at: str) -> str:
    # Minimal 56-ish columns: place_id, company_slug, name, phone, created, updated
    # DuckDB schema expects full column set — pad empties.
    cols = [""] * 56
    cols[0] = place_id
    cols[1] = place_id.lower()
    cols[2] = name
    cols[4] = updated_at
    cols[5] = updated_at
    return "\x1f".join(cols) + "\n"


def test_prospects_stations_compact_lww_and_current(
    tmp_path: Path, monkeypatch: Any
) -> None:
    from cocli.core import paths as paths_mod

    monkeypatch.setattr(paths_mod.paths, "root", tmp_path)

    index_dir = (
        tmp_path
        / "campaigns"
        / "t"
        / "indexes"
        / "google_maps_prospects"
    )
    index_dir.mkdir(parents=True)
    wal = index_dir / "wal" / "a"
    wal.mkdir(parents=True)
    checkpoint = index_dir / "prospects.usv"

    # Existing checkpoint (older)
    checkpoint.write_text(
        _usv_line("ChIJ1", "Old Name", "2026-01-01T00:00:00+00:00"),
        encoding="utf-8",
    )
    # WAL wins by updated_at
    (wal / "p1.usv").write_text(
        _usv_line("ChIJ1", "New Name", "2026-01-05T00:00:00+00:00")
        + _usv_line("ChIJ2", "Other", "2026-01-04T00:00:00+00:00"),
        encoding="utf-8",
    )

    assert (
        compact_prospects_local(
            index_dir,
            checkpoint_path=checkpoint,
            compactor_id="test",
        )
        is True
    )

    current = index_dir / "CURRENT"
    assert current.exists()
    meta = json.loads(current.read_text(encoding="utf-8"))
    assert meta["generation"] == 1
    assert "checkpoint" in meta
    assert (index_dir / meta["checkpoint"]).exists()

    text = checkpoint.read_text(encoding="utf-8")
    assert "New Name" in text
    assert "Other" in text
    assert "Old Name" not in text
    # WAL consumed
    assert list((index_dir / "wal").rglob("*.usv")) == []


def test_prospects_compact_idle_without_wal(tmp_path: Path) -> None:
    index_dir = tmp_path / "idx"
    index_dir.mkdir()
    (index_dir / "wal").mkdir()
    ck = index_dir / "prospects.usv"
    ck.write_text(_usv_line("ChIJ1", "Only", "2026-01-01T00:00:00+00:00"), encoding="utf-8")
    assert (
        compact_prospects_local(index_dir, checkpoint_path=ck, compactor_id="idle")
        is False
    )
