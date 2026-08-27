"""Prospects index: stations CURRENT commit + model-derived DuckDB fold."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cocli.core.stations_runtime import (
    _prospects_duckdb_columns,
    compact_prospects_local,
)
from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect


def _full_usv_line(
    place_id: str,
    name: str,
    updated_at: str,
    *,
    field_count: int | None = None,
    extra: dict[str, str] | None = None,
) -> str:
    """Build a USV row in current model order (optionally truncated for history)."""
    names = GoogleMapsProspect.usv_field_names()
    cols = [""] * len(names)
    idx = {n: i for i, n in enumerate(names)}
    cols[idx["place_id"]] = place_id
    cols[idx["slug"]] = place_id.lower()
    cols[idx["name"]] = name
    cols[idx["created_at"]] = updated_at
    cols[idx["updated_at"]] = updated_at
    for field_name, value in (extra or {}).items():
        cols[idx[field_name]] = value
    if field_count is not None:
        cols = cols[:field_count]
    return "\x1f".join(cols) + "\n"


def test_prospects_duckdb_columns_match_model() -> None:
    cols = _prospects_duckdb_columns()
    names = GoogleMapsProspect.usv_field_names()
    assert list(cols.keys()) == names
    assert len(cols) == len(GoogleMapsProspect.model_fields)
    # no stale dual-authority names
    assert "company_slug" not in cols
    assert "phone_1" not in cols
    assert "slug" in cols and "phone" in cols and "email" in cols
    assert cols["place_id"] == "VARCHAR"
    assert cols["version"] in ("INTEGER", "VARCHAR")  # projection from annotation


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

    checkpoint.write_text(
        _full_usv_line("ChIJ1", "Old Name", "2026-01-01T00:00:00+00:00"),
        encoding="utf-8",
    )
    (wal / "p1.usv").write_text(
        _full_usv_line("ChIJ1", "New Name", "2026-01-05T00:00:00+00:00")
        + _full_usv_line("ChIJ2", "Other", "2026-01-04T00:00:00+00:00"),
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
    assert list((index_dir / "wal").rglob("*.usv")) == []


def test_prospects_compact_accepts_shorter_historical_usv(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Append-only short rows (e.g. 55 vs 57) pad via DuckDB null_padding."""
    from cocli.core import paths as paths_mod

    monkeypatch.setattr(paths_mod.paths, "root", tmp_path)
    index_dir = tmp_path / "idx"
    index_dir.mkdir()
    (index_dir / "wal" / "x").mkdir(parents=True)
    ck = index_dir / "prospects.usv"
    n = len(GoogleMapsProspect.usv_field_names())
    short = max(1, n - 2)
    (index_dir / "wal" / "x" / "a.usv").write_text(
        _full_usv_line(
            "ChIJShort", "ShortRow", "2026-06-01T00:00:00+00:00", field_count=short
        ),
        encoding="utf-8",
    )
    assert (
        compact_prospects_local(index_dir, checkpoint_path=ck, compactor_id="short")
        is True
    )
    out = ck.read_text(encoding="utf-8")
    assert "ShortRow" in out
    # Output width is current model (padded)
    first = out.splitlines()[0]
    assert first.count("\x1f") + 1 == n


def test_prospects_compact_fold_is_field_level_not_whole_row(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """The real, live bug: an earlier gm-list-shaped row captured `category`;
    a later gm-details/enrichment-shaped write for the same place_id has no
    category (that writer never re-scrapes it) but does carry a corrected
    phone. A whole-row LWW fold picks the later row entirely and silently
    erases category. The fix must keep BOTH: the later phone AND the earlier
    category - that is the field-lineage guarantee, not just "newest row
    wins"."""
    from cocli.core import paths as paths_mod

    monkeypatch.setattr(paths_mod.paths, "root", tmp_path)

    index_dir = tmp_path / "campaigns" / "t" / "indexes" / "google_maps_prospects"
    index_dir.mkdir(parents=True)
    wal = index_dir / "wal" / "a"
    wal.mkdir(parents=True)
    checkpoint = index_dir / "prospects.usv"

    checkpoint.write_text(
        _full_usv_line(
            "ChIJ1",
            "Flooring Co",
            "2026-01-01T00:00:00+00:00",
            extra={"category": "Flooring contractor", "phone": "555-0001"},
        ),
        encoding="utf-8",
    )
    (wal / "p1.usv").write_text(
        _full_usv_line(
            "ChIJ1",
            "Flooring Co",
            "2026-01-05T00:00:00+00:00",
            extra={"category": "", "phone": "555-9999"},
        ),
        encoding="utf-8",
    )

    assert (
        compact_prospects_local(
            index_dir, checkpoint_path=checkpoint, compactor_id="field-lww"
        )
        is True
    )

    names = GoogleMapsProspect.usv_field_names()
    idx = {n: i for i, n in enumerate(names)}
    line = checkpoint.read_text(encoding="utf-8").splitlines()[0]
    parts = line.split("\x1f")

    assert parts[idx["phone"]] == "555-9999", "later row's phone must win"
    assert parts[idx["category"]] == "Flooring contractor", (
        "earlier row's category must survive - a later write with no "
        "category must not erase it"
    )


def test_prospects_compact_survives_literal_quote_characters_in_fields(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """DuckDB's read_csv defaults to the double-quote character as its quote
    character. A field containing several literal double-quote characters
    in a row (a real, confirmed scraper artifact seen in a mangled
    full_address value) breaks that default quoting and, combined with
    ignore_errors=True, silently drops the WHOLE ROW from the fold with no
    error surfaced - not just the offending field. This is a stronger bug
    than field-level erasure: the place_id vanishes from the checkpoint
    entirely. read_csv must be called with quote='' (treat the delimiter
    file as unquoted) to fix it."""
    from cocli.core import paths as paths_mod

    monkeypatch.setattr(paths_mod.paths, "root", tmp_path)

    index_dir = tmp_path / "campaigns" / "t" / "indexes" / "google_maps_prospects"
    index_dir.mkdir(parents=True)
    wal = index_dir / "wal" / "a"
    wal.mkdir(parents=True)
    checkpoint = index_dir / "prospects.usv"

    checkpoint.write_text(
        _full_usv_line(
            "ChIJQuoted",
            "Quote Corp",
            "2026-01-01T00:00:00+00:00",
            extra={
                "category": "Flooring contractor",
                "phone": "555-0001",
                "full_address": '"""""1501 Heritage Pkwy # 105"""""',
            },
        ),
        encoding="utf-8",
    )
    (wal / "p1.usv").write_text(
        _full_usv_line(
            "ChIJQuoted",
            "Quote Corp",
            "2026-01-05T00:00:00+00:00",
            extra={"phone": "555-9999"},
        ),
        encoding="utf-8",
    )

    assert (
        compact_prospects_local(
            index_dir, checkpoint_path=checkpoint, compactor_id="quote-survival"
        )
        is True
    )

    lines = [ln for ln in checkpoint.read_text(encoding="utf-8").splitlines() if ln]
    assert len(lines) == 1, "the row must not be silently dropped entirely"

    names = GoogleMapsProspect.usv_field_names()
    idx = {n: i for i, n in enumerate(names)}
    parts = lines[0].split("\x1f")
    assert parts[idx["place_id"]] == "ChIJQuoted"
    assert parts[idx["phone"]] == "555-9999"
    assert parts[idx["category"]] == "Flooring contractor"


def test_prospects_compact_does_not_csv_quote_hash_prefixed_names(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """DuckDB COPY quotes fields that start with '#' by default (CSV comment
    char). Combined with read_csv(quote=''), those wrappers become literal
    characters on the next load — so compact undoes clean-quote-corruption
    for names like # 1 Hardwood Flooring."""
    from cocli.core import paths as paths_mod

    monkeypatch.setattr(paths_mod.paths, "root", tmp_path)

    index_dir = tmp_path / "campaigns" / "t" / "indexes" / "google_maps_prospects"
    index_dir.mkdir(parents=True)
    wal = index_dir / "wal" / "a"
    wal.mkdir(parents=True)
    checkpoint = index_dir / "prospects.usv"
    checkpoint.write_text(
        _full_usv_line(
            "ChIJHashNameaaaaaaaaaa",
            "# 1 Hardwood Flooring",
            "2026-01-01T00:00:00+00:00",
        ),
        encoding="utf-8",
    )
    (wal / "touch.usv").write_text(
        _full_usv_line(
            "ChIJHashNameaaaaaaaaaa",
            "# 1 Hardwood Flooring",
            "2026-01-02T00:00:00+00:00",
        ),
        encoding="utf-8",
    )

    assert (
        compact_prospects_local(
            index_dir, checkpoint_path=checkpoint, compactor_id="hash-name"
        )
        is True
    )

    names = GoogleMapsProspect.usv_field_names()
    idx = {n: i for i, n in enumerate(names)}
    parts = checkpoint.read_text(encoding="utf-8").splitlines()[0].split("\x1f")
    assert parts[idx["name"]] == "# 1 Hardwood Flooring"
    assert '"' not in parts[idx["name"]]


def test_prospects_compact_fold_ignores_garbage_updated_at_as_tiebreaker(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """A corrupted updated_at (e.g. a field-misalignment artifact leaving a
    non-date string there) must not out-rank a real ISO timestamp just
    because letters sort after digits lexicographically."""
    from cocli.core import paths as paths_mod

    monkeypatch.setattr(paths_mod.paths, "root", tmp_path)

    index_dir = tmp_path / "campaigns" / "t" / "indexes" / "google_maps_prospects"
    index_dir.mkdir(parents=True)
    wal = index_dir / "wal" / "a"
    wal.mkdir(parents=True)
    checkpoint = index_dir / "prospects.usv"

    checkpoint.write_text(
        _full_usv_line(
            "ChIJ1",
            "Real Row",
            "2026-01-01T00:00:00+00:00",
            extra={"category": "Flooring contractor"},
        ),
        encoding="utf-8",
    )
    (wal / "p1.usv").write_text(
        _full_usv_line(
            "ChIJ1",
            "Garbage Row",
            "Epoxy Floo",
            extra={"category": ""},
        ),
        encoding="utf-8",
    )

    assert (
        compact_prospects_local(
            index_dir, checkpoint_path=checkpoint, compactor_id="garbage-key"
        )
        is True
    )

    names = GoogleMapsProspect.usv_field_names()
    idx = {n: i for i, n in enumerate(names)}
    line = checkpoint.read_text(encoding="utf-8").splitlines()[0]
    parts = line.split("\x1f")

    assert parts[idx["category"]] == "Flooring contractor"
    assert parts[idx["name"]] == "Real Row"


def test_prospects_compact_idle_without_wal(tmp_path: Path) -> None:
    index_dir = tmp_path / "idx"
    index_dir.mkdir()
    (index_dir / "wal").mkdir()
    ck = index_dir / "prospects.usv"
    ck.write_text(
        _full_usv_line("ChIJ1", "Only", "2026-01-01T00:00:00+00:00"),
        encoding="utf-8",
    )
    assert (
        compact_prospects_local(index_dir, checkpoint_path=ck, compactor_id="idle")
        is False
    )


def test_schema_generation_log_appends_on_datapackage_write(tmp_path: Path) -> None:
    GoogleMapsProspect.save_datapackage(tmp_path, force=True)
    log = tmp_path / "schema_generations.jsonl"
    ledger = tmp_path / "schema_ledger.json"
    assert log.exists()
    assert ledger.exists()
    line = log.read_text(encoding="utf-8").strip().splitlines()[-1]
    rec = json.loads(line)
    assert rec["schema_hash"] == GoogleMapsProspect.get_schema_hash()
    assert rec["field_count"] == len(GoogleMapsProspect.usv_field_names())
    assert rec["fields"][0] == "place_id"
