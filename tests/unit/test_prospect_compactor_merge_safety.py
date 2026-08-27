"""compact_prospects_to_checkpoint() must merge per-field, not pure
last-write-wins by row.

GoogleMapsDetailsProcessor.merge_with_existing() already protects the
single-attempt-at-a-time case, but its existing-lookup
(GoogleMapsProspect.get_by_place_id) only checks the COMPACTED
CHECKPOINT, not raw WAL shards - so any two scrapes for the same
place_id that both land in WAL before a compaction ever runs (same node
back-to-back, or two different Pi nodes each working from their own
local disk) are invisible to each other's merge. Compaction is the only
place that reconciles them, so it must itself be hollow-aware per field,
not just "keep the whole row with the latest updated_at." See task-agent
ticket
per-field-hollow-check-merge-safety-for-gm-details-prospects-index-compaction.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cocli.core.paths import paths
from cocli.core.prospect_compactor import compact_prospects_to_checkpoint
from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
from cocli.utils.usv_utils import USVDictReader


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths.root = tmp_path
    monkeypatch.delenv("COCLI_CAMPAIGN", raising=False)


def _write_wal_row(campaign: str, prospect: GoogleMapsProspect, filename: str) -> None:
    wal_dir = paths.campaign(campaign).index("google_maps_prospects").wal
    wal_dir.mkdir(parents=True, exist_ok=True)
    with open(wal_dir / filename, "w", encoding="utf-8") as f:
        f.write(prospect.to_usv())


def _read_checkpoint_row(campaign: str, place_id: str) -> dict:
    # Checkpoint files are headerless USV - fieldnames must be supplied
    # explicitly, or USVDictReader treats the first data row as headers.
    checkpoint = paths.campaign(campaign).index("google_maps_prospects").checkpoint
    with open(checkpoint, "r", encoding="utf-8") as f:
        reader = USVDictReader(f, fieldnames=GoogleMapsProspect.usv_field_names())
        for row in reader:
            if row.get("place_id") == place_id:
                return row
    raise AssertionError(f"place_id {place_id} not found in compacted checkpoint")


def test_older_richer_row_survives_a_newer_sparse_row_for_same_place_id() -> None:
    campaign = "test-campaign"
    place_id = "ChIJtestplace0000000000000000000"
    older_ts = datetime.now(timezone.utc) - timedelta(days=2)
    newer_ts = datetime.now(timezone.utc)

    rich = GoogleMapsProspect(
        place_id=place_id,
        slug="acme-flooring",
        name="Acme Flooring",
        phone="15551234567",
        website="https://acmeflooring.com",
        domain="acmeflooring.com",
        average_rating="4.8",
        reviews_count="42",
        hours="Mon-Fri 8am-5pm",
        created_at=older_ts,
        updated_at=older_ts,
        processed_by="cocli5x0-details-1",
    )
    _write_wal_row(campaign, rich, "shard1.usv")

    # A later re-scrape that found the place but not much else - phone,
    # website, rating, hours all come back empty.
    sparse = GoogleMapsProspect(
        place_id=place_id,
        slug="acme-flooring",
        name="Acme Flooring",
        created_at=newer_ts,
        updated_at=newer_ts,
        processed_by="cocli5x1-details-1",
    )
    _write_wal_row(campaign, sparse, "shard2.usv")

    count = compact_prospects_to_checkpoint(campaign)
    assert count == 1

    row = _read_checkpoint_row(campaign, place_id)
    # Merge-eligible fields: older row's real values survive.
    assert row["phone"] == "15551234567"
    assert row["website"] == "https://acmeflooring.com"
    assert row["average_rating"] == "4.8"
    assert row["hours"] == "Mon-Fri 8am-5pm"
    # Never-merge fields: reflect the WINNING (latest) row's own values,
    # not a stale older timestamp/attribution.
    assert row["updated_at"] == newer_ts.isoformat()
    assert row["processed_by"] == "cocli5x1-details-1"


def test_newer_row_with_real_new_value_still_wins_for_that_field() -> None:
    campaign = "test-campaign"
    place_id = "ChIJtestplace1111111111111111111"
    older_ts = datetime.now(timezone.utc) - timedelta(days=2)
    newer_ts = datetime.now(timezone.utc)

    older = GoogleMapsProspect(
        place_id=place_id,
        slug="acme-flooring",
        name="Acme Flooring",
        phone="15551234567",
        created_at=older_ts,
        updated_at=older_ts,
    )
    _write_wal_row(campaign, older, "shard1.usv")

    newer = GoogleMapsProspect(
        place_id=place_id,
        slug="acme-flooring",
        name="Acme Flooring",
        phone="15559999999",  # a real, different phone number found later
        created_at=newer_ts,
        updated_at=newer_ts,
    )
    _write_wal_row(campaign, newer, "shard2.usv")

    compact_prospects_to_checkpoint(campaign)

    row = _read_checkpoint_row(campaign, place_id)
    assert row["phone"] == "15559999999"
