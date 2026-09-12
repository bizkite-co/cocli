"""Compaction coverage lists stations read vs sitting unread on disk."""

from __future__ import annotations

from pathlib import Path

from cocli.core.compaction_coverage import (
    count_usv_records,
    coverage_for,
)


def test_count_usv_records_counts_nonempty_lines(tmp_path: Path) -> None:
    root = tmp_path / "results"
    nested = root / "3" / "33.4"
    nested.mkdir(parents=True)
    (nested / "a.usv").write_text("row1\nrow2\n\n")
    (nested / "b.usv").write_text("row3\n")
    (nested / "skip.txt").write_text("ignored\n")
    assert count_usv_records(root) == 3
    assert count_usv_records(tmp_path / "missing") == 0


def test_manifest_flags_declared_source_not_read(tmp_path: Path) -> None:
    results = tmp_path / "queues" / "gm-list" / "completed" / "results"
    results.mkdir(parents=True)
    (results / "tile.usv").write_text("a\nb\nc\n")
    wal = tmp_path / "indexes" / "google_maps_prospects" / "wal"
    wal.mkdir(parents=True)
    (wal / "x.usv").write_text("w1\n")

    text = coverage_for(
        "google_maps_prospects",
        "turboship",
        tmp_path,
        run_id="run_1785457576",
        records_read={"prospects-wal": 1},
    ).format_human()

    assert "Compaction: google_maps_prospects (turboship), run_1785457576" in text
    assert "indexes/google_maps_prospects/wal/" in text
    assert "1 records" in text
    assert "Sources NOT read" in text
    assert "queues/gm-list/completed/results/" in text
    assert "3 records available" in text


def test_manifest_none_unread_when_all_declared_sources_read(tmp_path: Path) -> None:
    results = tmp_path / "queues" / "gm-list" / "completed" / "results"
    results.mkdir(parents=True)
    (results / "tile.usv").write_text("a\n")
    text = coverage_for(
        "google_maps_prospects",
        "turboship",
        tmp_path,
        run_id="run_1",
        records_read={"gm-list-results": 1, "prospects-wal": 4},
    ).format_human()
    assert "Sources NOT read" in text
    assert "(none)" in text.split("Sources NOT read")[1]
    assert "gm-list-results" in text or "completed/results" in text
