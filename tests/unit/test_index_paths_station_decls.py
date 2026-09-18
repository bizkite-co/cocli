"""IndexPaths phases come from StationDecl; runs is layout, not a phase."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from cocli.core.ordinant import IndexIdentity
from cocli.core.paths import paths
from cocli.station_defs.campaigns.indexes import INDEX_RUNS_LAYOUT
from cocli.station_defs.campaigns.indexes.google_maps_prospects import (
    PROSPECTS_INDEX,
)
from stations.segments import collect_phases


def test_prospects_decl_is_wal_and_processing_not_runs_archive_inbox() -> None:
    ph = collect_phases(PROSPECTS_INDEX.segments)
    assert ph is not None
    assert ph.names == ("wal", "processing")
    assert INDEX_RUNS_LAYOUT not in ph.names
    assert not ph.is_phase("runs")
    assert not ph.is_phase("archive")
    assert not ph.is_phase("inbox")


def test_index_paths_declared_phases_follow_station(
    tmp_path: Path,
) -> None:
    with patch("cocli.core.paths.paths.root", tmp_path):
        prospects = paths.campaign("camp").index("google_maps_prospects")
        assert prospects.index_name == "google_maps_prospects"
        assert prospects.declared_phases() == ("wal", "processing")

        emails = paths.campaign("camp").index("emails")
        assert emails.index_name == "emails"
        assert emails.declared_phases() == ("inbox", "shards")

        undeclared = paths.campaign("camp").index("company_cache")
        assert undeclared.index_name == "company_cache"
        assert undeclared.declared_phases() is None


def test_index_paths_runs_is_layout_and_does_not_raise(
    tmp_path: Path,
) -> None:
    with patch("cocli.core.paths.paths.root", tmp_path):
        prospects = paths.campaign("camp").index(IndexIdentity.PROSPECTS)
        assert prospects.runs.name == INDEX_RUNS_LAYOUT
        assert prospects.wal.name == "wal"
        # Undeclared children and undeclared families must not raise yet.
        assert prospects.state("archive").name == "archive"
        assert prospects.state("inbox").name == "inbox"
        cache = paths.campaign("camp").index("company_cache")
        assert cache.wal.name == "wal"
        assert cache.runs.name == INDEX_RUNS_LAYOUT
        assert cache.checkpoint.name == "company_cache.usv"
        assert prospects.checkpoint.name == "prospects.usv"
