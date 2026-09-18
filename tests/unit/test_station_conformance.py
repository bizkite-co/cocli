"""Index-station conformance audit (0010): reports drift, never raises."""

from __future__ import annotations

from pathlib import Path

from cocli.core.audit.station_conformance import (
    FindingKind,
    audit_index_stations,
    summarize_index_station_audit,
)


def _build_tree(tmp_path: Path) -> Path:
    """A campaigns root reproducing the drift shapes found in production."""
    indexes = tmp_path / "campaigns" / "camp" / "indexes"

    # Declared family, canonical layout plus a stray per-domain directory
    # (roadmap/indexes/emails has 560 of these next to inbox/ and shards/).
    (indexes / "emails" / "inbox").mkdir(parents=True)
    (indexes / "emails" / "shards").mkdir()
    (indexes / "emails" / "deaconwealth.com").mkdir()

    # Declared family whose decl omits directories the code actually uses:
    # IndexPaths exposes .runs, but PROSPECTS_INDEX declares only wal/processing.
    (indexes / "google_maps_prospects" / "wal").mkdir(parents=True)
    (indexes / "google_maps_prospects" / "runs").mkdir()

    # Undeclared family, and a file sitting in the indexes/ root.
    (indexes / "company_cache").mkdir()
    (indexes / "location-prospects.csv").write_text("x", encoding="utf-8")

    return tmp_path / "campaigns"


def test_audit_reports_undeclared_family_and_naked_file(tmp_path: Path) -> None:
    audit = audit_index_stations(campaigns_root=_build_tree(tmp_path))
    findings = audit.findings

    undeclared = [f for f in findings if f.kind is FindingKind.UNDECLARED_FAMILY]
    assert [f.index_name for f in undeclared] == ["company_cache"]

    naked = [f for f in findings if f.kind is FindingKind.NAKED_FILE]
    assert [f.index_name for f in naked] == ["location-prospects.csv"]
    assert audit.families_compared == 3
    assert audit.campaigns_scanned == 1
    assert audit.campaigns_with_indexes == 1


def test_audit_reports_undeclared_children_of_a_declared_index(
    tmp_path: Path,
) -> None:
    findings = audit_index_stations(campaigns_root=_build_tree(tmp_path)).findings
    children = {
        f.index_name: f
        for f in findings
        if f.kind is FindingKind.UNDECLARED_CHILD
    }

    assert "deaconwealth.com" in children["emails"].detail
    assert "runs" in children["google_maps_prospects"].detail
    # inbox/ and shards/ are declared phases of EMAIL_INDEX, so the stray
    # per-domain directory is the only thing counted as drift.
    assert children["emails"].detail.startswith("1 director")


def test_audit_reports_declared_phase_absent_as_its_own_kind(
    tmp_path: Path,
) -> None:
    findings = audit_index_stations(campaigns_root=_build_tree(tmp_path)).findings
    absent = [f for f in findings if f.kind is FindingKind.DECLARED_PHASE_ABSENT]

    # PROSPECTS_INDEX declares processing/; the tree above has only wal/.
    assert any(
        f.index_name == "google_maps_prospects" and "processing" in f.detail
        for f in absent
    )


def test_audit_can_scope_to_one_campaign_and_never_raises(tmp_path: Path) -> None:
    root = _build_tree(tmp_path)
    (root / "other" / "indexes" / "company_cache").mkdir(parents=True)

    all_campaigns = audit_index_stations(campaigns_root=root)
    assert {f.campaign for f in all_campaigns.findings} == {
        "camp",
        "other",
    }
    scoped = audit_index_stations(campaigns_root=root, campaign="other")
    assert {f.campaign for f in scoped.findings} == {"other"}
    assert scoped.campaigns_scanned == 1
    assert scoped.families_compared == 1

    # Missing root is not an error - the audit is read-only and total.
    missing = audit_index_stations(campaigns_root=tmp_path / "nope")
    assert missing.findings == []
    assert missing.families_compared == 0
    assert missing.campaigns_scanned == 0


def test_audit_empty_tree_is_not_a_pass(tmp_path: Path) -> None:
    """Campaign stubs with no indexes/ must not summarize as a match."""
    campaigns = tmp_path / "campaigns"
    (campaigns / "roadmap").mkdir(parents=True)
    (campaigns / "turboship" / "queues").mkdir(parents=True)

    audit = audit_index_stations(campaigns_root=campaigns)
    assert audit.families_compared == 0
    assert audit.campaigns_scanned == 2
    assert audit.campaigns_with_indexes == 0
    assert audit.findings == []
    summary = summarize_index_station_audit(audit)
    assert "Nothing compared" in summary
    assert "not a pass" in summary


def test_audit_matching_declared_family_reports_how_many_compared(
    tmp_path: Path,
) -> None:
    indexes = tmp_path / "campaigns" / "camp" / "indexes"
    (indexes / "emails" / "inbox").mkdir(parents=True)
    (indexes / "emails" / "shards").mkdir()

    audit = audit_index_stations(campaigns_root=tmp_path / "campaigns")
    assert audit.findings == []
    assert audit.families_compared == 1
    summary = summarize_index_station_audit(audit)
    assert summary.startswith("1 index family")
