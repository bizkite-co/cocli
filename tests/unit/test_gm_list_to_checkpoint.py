"""compact_gm_list_results: gm-list results -> prospects checkpoint merge.

The real, live bug this pins: the same place_id legitimately appears in
multiple gm-list result files (overlapping geo-tiles / different keyword
searches each re-discovering the same business). Without reducing those
duplicates to one row per place_id first, the old code joined the raw,
un-reduced rows straight into the checkpoint merge and broke ties by
`discovery_tile_id` - a tile-coordinate string, not a timestamp - so it
could arbitrarily pick the one duplicate row that happened to be missing
`category`, discarding a category another duplicate row for the same place
actually had. See scripts/sql/gm_prospects_yield/queries/
04_gm_results_duplicate_place_ids.sql and 06_gm_results_reduced_per_place_id.sql
for the standalone diagnostics that sized this before it was fixed here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cocli.core.transformers.gm_list_to_checkpoint import compact_gm_list_results
from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect

_GM_FIELDS = [
    "place_id",
    "company_slug",
    "name",
    "category",
    "phone",
    "domain",
    "reviews_count",
    "average_rating",
    "street_address",
    "gmb_url",
    "discovery_phrase",
    "discovery_tile_id",
    "html",
]


def _gm_row(**values: str) -> str:
    cols = [values.get(f, "") for f in _GM_FIELDS]
    return "\x1f".join(cols) + "\n"


def _checkpoint_line(place_id: str, name: str, updated_at: str, **extra: str) -> str:
    names = GoogleMapsProspect.usv_field_names()
    cols = [""] * len(names)
    idx = {n: i for i, n in enumerate(names)}
    cols[idx["place_id"]] = place_id
    cols[idx["slug"]] = place_id.lower()
    cols[idx["name"]] = name
    cols[idx["created_at"]] = updated_at
    cols[idx["updated_at"]] = updated_at
    for field_name, value in extra.items():
        cols[idx[field_name]] = value
    return "\x1f".join(cols) + "\n"


def _setup_campaign(tmp_path: Path, monkeypatch: Any, campaign: str = "t") -> Path:
    from cocli.core import paths as paths_mod

    monkeypatch.setattr(paths_mod.paths, "root", tmp_path)

    index_dir = tmp_path / "campaigns" / campaign / "indexes" / "google_maps_prospects"
    index_dir.mkdir(parents=True)
    GoogleMapsProspect.save_datapackage(index_dir, force=True)

    results_dir = (
        tmp_path / "campaigns" / campaign / "queues" / "gm-list" / "completed" / "results"
    )
    results_dir.mkdir(parents=True)
    return index_dir


def test_duplicate_place_id_across_files_does_not_lose_category(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Two gm-list result files re-discover the same place_id: one (from an
    earlier tile-string that would sort AFTER the other) carries category,
    the other (sorting first) does not. The merge must keep the category
    regardless of which duplicate the old tile-id ordering would have
    arbitrarily preferred."""
    campaign = "t"
    index_dir = _setup_campaign(tmp_path, monkeypatch, campaign)
    checkpoint = index_dir / "prospects.usv"
    checkpoint.write_text(
        _checkpoint_line("ChIJDup00000000000000000001", "Old Name", "2026-01-01T00:00:00+00:00"),
        encoding="utf-8",
    )

    results_dir = (
        tmp_path / "campaigns" / campaign / "queues" / "gm-list" / "completed" / "results"
    )
    # This tile-id string sorts AFTER "a_tile" lexicographically, so the old
    # whole-row arbitrary pick (ordered by discovery_tile_id) would have
    # chosen this null-category row as "the winner" and discarded the other.
    (results_dir / "tile_b.usv").write_text(
        _gm_row(
            place_id="ChIJDup00000000000000000001",
            name="Flooring Co",
            category="",
            phone="555-0002",
            discovery_tile_id="z_tile",
        ),
        encoding="utf-8",
    )
    (results_dir / "tile_a.usv").write_text(
        _gm_row(
            place_id="ChIJDup00000000000000000001",
            name="Flooring Co",
            category="Flooring contractor",
            phone="",
            discovery_tile_id="a_tile",
        ),
        encoding="utf-8",
    )

    merged_count = compact_gm_list_results(campaign)
    assert merged_count == 1

    names = GoogleMapsProspect.usv_field_names()
    idx = {n: i for i, n in enumerate(names)}
    line = checkpoint.read_text(encoding="utf-8").splitlines()[0]
    parts = line.split("\x1f")

    assert parts[idx["category"]] == "Flooring contractor", (
        "category from one duplicate result file must survive even though "
        "another duplicate for the same place_id sorts later by tile_id "
        "and has no category"
    )
    assert parts[idx["phone"]] == "555-0002", "phone from the other duplicate must also survive"


def test_backup_of_existing_checkpoint_is_timestamped(
    tmp_path: Path, monkeypatch: Any
) -> None:
    import re

    campaign = "t"
    index_dir = _setup_campaign(tmp_path, monkeypatch, campaign)
    checkpoint = index_dir / "prospects.usv"
    checkpoint.write_text(
        _checkpoint_line("ChIJBackup000000000000000001", "Name", "2026-01-01T00:00:00+00:00"),
        encoding="utf-8",
    )

    results_dir = (
        tmp_path / "campaigns" / campaign / "queues" / "gm-list" / "completed" / "results"
    )
    (results_dir / "a.usv").write_text(
        _gm_row(place_id="ChIJBackup000000000000000001", name="Name", category="Flooring"),
        encoding="utf-8",
    )

    compact_gm_list_results(campaign)

    backups = list(index_dir.glob("prospects.usv.*.bak"))
    assert len(backups) == 1
    assert re.search(r"prospects\.usv\.\d{8}T\d{6}Z\.bak$", backups[0].name)
    assert not (index_dir / "prospects.usv.bak").exists(), (
        "must never write the old unstamped filename that a re-run could "
        "silently clobber"
    )
