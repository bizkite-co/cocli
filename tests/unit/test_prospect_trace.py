"""Unit tests for cocli.core.prospect_trace: the reusable identity-tracing
station-check mechanism, and the google_maps_prospects-specific verdict
logic built on top of it.

See task-agent ticket
promote-trace-dropped-prospects.py-to-a-permanent-cocli-command-for-google-maps-prospects
and its companion in the stations repo,
identity-trace-capability-given-a-workflow-item-id-walk-all-declared-stations-and-report-presencestate.
"""

from pathlib import Path
from typing import Dict

from cocli.core.prospect_trace import (
    US,
    CheckpointPresenceCheck,
    GmListResultsCheck,
    PrebuiltSetCheck,
    ProspectDomainIndex,
    QueueBucketCheck,
    StationResult,
    categorize_verdict,
    diagnose_prospect_trace,
    find_gm_list_rows,
    trace_identities,
    trace_identity,
)


def test_gm_list_results_check_finds_hits_across_multiple_files(tmp_path: Path) -> None:
    results_dir = tmp_path / "results"
    (results_dir / "40.7" / "-74.0").mkdir(parents=True)
    (results_dir / "40.7" / "-74.0" / "commercial-vinyl-flooring-contractor.usv").write_text(
        f"PLACE_A{US}Some Name\nPLACE_B{US}Other Name\n"
    )
    (results_dir / "40.6" / "-73.8").mkdir(parents=True)
    (results_dir / "40.6" / "-73.8" / "rubber-flooring-contractor.usv").write_text(
        f"PLACE_A{US}Some Name\n"
    )

    check = GmListResultsCheck(results_dir)

    hit = check.check("PLACE_A")
    assert hit.state == "found"
    assert "2 hit(s)" in hit.detail

    miss = check.check("PLACE_C")
    assert miss.state == "absent"


def test_gm_list_results_check_handles_missing_dir(tmp_path: Path) -> None:
    check = GmListResultsCheck(tmp_path / "does-not-exist")
    assert check.check("anything").state == "absent"


def test_queue_bucket_check_distinguishes_completed_pending_failed_never(tmp_path: Path) -> None:
    completed = tmp_path / "completed"
    pending = tmp_path / "pending" / "P"
    failed = tmp_path / "failed"
    completed.mkdir(parents=True)
    pending.mkdir(parents=True)
    failed.mkdir(parents=True)

    (completed / "PLACE_DONE.json").write_text("{}")
    (pending / "PLACE_PENDING").write_text("")
    (failed / "PLACE_FAILED.json").write_text("{}")

    check = QueueBucketCheck("gm-details", completed, tmp_path / "pending", failed)

    assert check.check("PLACE_DONE").state == "completed"
    assert check.check("PLACE_PENDING").state == "pending"
    assert check.check("PLACE_FAILED").state == "failed"
    assert check.check("PLACE_NEVER").state == "never seen"


def test_queue_bucket_check_ignores_lease_files_in_pending(tmp_path: Path) -> None:
    pending = tmp_path / "pending" / "P"
    pending.mkdir(parents=True)
    (pending / "PLACE_X.lease").write_text("{}")

    check = QueueBucketCheck("gm-details", tmp_path / "completed", tmp_path / "pending")

    # Only a lease file exists (the item itself was never written) - not "pending".
    assert check.check("PLACE_X").state == "never seen"


def test_checkpoint_presence_check(tmp_path: Path) -> None:
    checkpoint = tmp_path / "prospects.usv"
    checkpoint.write_text(f"PLACE_A{US}rest of row\nPLACE_B{US}rest of row\n")

    check = CheckpointPresenceCheck(checkpoint)

    assert check.check("PLACE_A").state == "present"
    assert check.check("PLACE_Z").state == "absent"


def test_checkpoint_presence_check_missing_file(tmp_path: Path) -> None:
    check = CheckpointPresenceCheck(tmp_path / "nonexistent.usv")
    assert check.check("PLACE_A").state == "absent"


def test_prebuilt_set_check() -> None:
    check = PrebuiltSetCheck("pi-wal", {"PLACE_A", "PLACE_B"})
    assert check.check("PLACE_A").state == "present"
    assert check.check("PLACE_Z").state == "absent"


def test_trace_identity_walks_every_check() -> None:
    checks = [
        PrebuiltSetCheck("station-1", {"X"}),
        PrebuiltSetCheck("station-2", set()),
    ]
    result = trace_identity(checks, "X")  # type: ignore[arg-type]
    assert result["station-1"].state == "present"
    assert result["station-2"].state == "absent"


def test_trace_identities_produces_one_row_per_identity() -> None:
    checks = [PrebuiltSetCheck("station-1", {"X"})]
    rows = trace_identities(checks, ["X", "Y"])  # type: ignore[arg-type]
    assert [r.identity for r in rows] == ["X", "Y"]
    assert rows[0].results["station-1"].state == "present"
    assert rows[1].results["station-1"].state == "absent"


def _states(gm_list: str, gm_details: str, pi_wal: str, checkpoint: str) -> Dict[str, StationResult]:
    return {
        "gm-list": StationResult(station="gm-list", state=gm_list),
        "gm-details": StationResult(station="gm-details", state=gm_details),
        "pi-wal": StationResult(station="pi-wal", state=pi_wal),
        "checkpoint": StationResult(station="checkpoint", state=checkpoint),
    }


def test_diagnose_present_in_checkpoint_wins_first() -> None:
    verdict = diagnose_prospect_trace(
        _states(gm_list="found", gm_details="completed", pi_wal="present", checkpoint="present")
    )
    assert verdict == "present in current checkpoint"


def test_diagnose_wal_has_it_but_fold_dropped_it() -> None:
    verdict = diagnose_prospect_trace(
        _states(gm_list="found", gm_details="completed", pi_wal="present", checkpoint="absent")
    )
    assert "FOLD BUG" in verdict


def test_diagnose_gm_details_completed_never_reached_wal() -> None:
    # The exact real-incident case: 212carpet.com, acswoodfloors.com, a1nwcfloor.com.
    verdict = diagnose_prospect_trace(
        _states(gm_list="found", gm_details="completed", pi_wal="absent", checkpoint="absent")
    )
    assert "WAL-write or sync gap" in verdict


def test_diagnose_rediscovered_but_gm_details_gap() -> None:
    verdict = diagnose_prospect_trace(
        _states(gm_list="found", gm_details="never seen", pi_wal="absent", checkpoint="absent")
    )
    # Renamed 2026-08-18 from "enrichment gap" to "detailing gap" - the old
    # label was actually about gm-details, which became confusing once the
    # real enrichment-stage check (see below) was added alongside it.
    assert "detailing gap" in verdict
    assert "never seen" in verdict


def test_diagnose_never_rediscovered() -> None:
    verdict = diagnose_prospect_trace(
        _states(gm_list="absent", gm_details="never seen", pi_wal="absent", checkpoint="absent")
    )
    assert "never rediscovered" in verdict


def test_find_gm_list_rows_returns_full_row_for_requested_ids(tmp_path: Path) -> None:
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    row = US.join(
        [
            "PLACE_A", "slug-a", "Name A", "Category A", "555-1234", "example.com",
            "12", "4.5", "123 Main St", "https://maps.example/a",
            "flooring contractor", "40.7_-74.0", "<html/>",
        ]
    )
    (results_dir / "q.usv").write_text(row + "\nPLACE_B" + US + "Name B\n")

    found = find_gm_list_rows(results_dir, {"PLACE_A"})

    assert found["PLACE_A"]["name"] == "Name A"
    assert found["PLACE_A"]["company_slug"] == "slug-a"
    assert found["PLACE_A"]["category"] == "Category A"
    assert found["PLACE_A"]["discovery_phrase"] == "flooring contractor"
    assert found["PLACE_A"]["discovery_tile_id"] == "40.7_-74.0"
    assert "PLACE_B" not in found


def test_find_gm_list_rows_missing_id_absent_from_result(tmp_path: Path) -> None:
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "q.usv").write_text(f"PLACE_A{US}Name A\n")

    found = find_gm_list_rows(results_dir, {"PLACE_MISSING"})

    assert found == {}


def test_find_gm_list_rows_empty_place_ids_returns_empty(tmp_path: Path) -> None:
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "q.usv").write_text(f"PLACE_A{US}Name A\n")

    assert find_gm_list_rows(results_dir, set()) == {}


def test_find_gm_list_rows_missing_dir_returns_empty(tmp_path: Path) -> None:
    assert find_gm_list_rows(tmp_path / "nonexistent", {"PLACE_A"}) == {}


def _prospect_row(fieldnames: list, **overrides: str) -> str:
    values = {name: "" for name in fieldnames}
    values.update(overrides)
    return US.join(values[name] for name in fieldnames)


def test_gm_list_results_check_all_identities(tmp_path: Path) -> None:
    results_dir = tmp_path / "results" / "40.7" / "-74.0"
    results_dir.mkdir(parents=True)
    (results_dir / "q.usv").write_text(f"PLACE_A{US}Name\nPLACE_B{US}Name\n")

    check = GmListResultsCheck(tmp_path / "results")

    assert check.all_identities() == {"PLACE_A", "PLACE_B"}


def test_checkpoint_presence_check_all_identities(tmp_path: Path) -> None:
    checkpoint = tmp_path / "prospects.usv"
    checkpoint.write_text(f"PLACE_A{US}rest\nPLACE_B{US}rest\n")

    check = CheckpointPresenceCheck(checkpoint)

    assert check.all_identities() == {"PLACE_A", "PLACE_B"}


def test_prospect_domain_index_reads_domain_from_checkpoint(tmp_path: Path) -> None:
    from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect

    fieldnames = list(GoogleMapsProspect.model_fields.keys())
    checkpoint = tmp_path / "prospects.usv"
    row_with_domain = _prospect_row(fieldnames, place_id="PLACE_A", domain="example.com")
    row_without_domain = _prospect_row(fieldnames, place_id="PLACE_B", domain="")
    checkpoint.write_text(row_with_domain + "\n" + row_without_domain + "\n")

    index = ProspectDomainIndex(checkpoint)

    assert index.get_domain("PLACE_A") == "example.com"
    assert index.get_domain("PLACE_B") is None
    assert index.get_domain("PLACE_MISSING") is None


def test_prospect_domain_index_falls_back_to_wal_when_not_in_checkpoint(tmp_path: Path) -> None:
    from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect

    fieldnames = list(GoogleMapsProspect.model_fields.keys())
    checkpoint = tmp_path / "prospects.usv"
    checkpoint.write_text("")  # empty - PLACE_A not compacted yet

    wal_root = tmp_path / "wal"
    shard_dir = wal_root / "PL"
    shard_dir.mkdir(parents=True)
    (shard_dir / "PLACE_A.usv").write_text(
        _prospect_row(fieldnames, place_id="PLACE_A", domain="wal-example.com")
    )

    index = ProspectDomainIndex(checkpoint, wal_root)

    assert index.get_domain("PLACE_A") == "wal-example.com"


def test_prospect_domain_index_checkpoint_wins_over_wal(tmp_path: Path) -> None:
    from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect

    fieldnames = list(GoogleMapsProspect.model_fields.keys())
    checkpoint = tmp_path / "prospects.usv"
    checkpoint.write_text(
        _prospect_row(fieldnames, place_id="PLACE_A", domain="checkpoint-example.com") + "\n"
    )

    wal_root = tmp_path / "wal"
    shard_dir = wal_root / "PL"
    shard_dir.mkdir(parents=True)
    (shard_dir / "PLACE_A.usv").write_text(
        _prospect_row(fieldnames, place_id="PLACE_A", domain="stale-wal-example.com")
    )

    index = ProspectDomainIndex(checkpoint, wal_root)

    assert index.get_domain("PLACE_A") == "checkpoint-example.com"


def test_diagnose_present_in_checkpoint_no_domain() -> None:
    verdict = diagnose_prospect_trace(
        _states(gm_list="found", gm_details="completed", pi_wal="present", checkpoint="present"),
        enrichment=StationResult(station="enrichment", state="no domain"),
    )
    assert "no domain found yet" in verdict
    assert categorize_verdict(verdict) == "no gap (pre-enrichment)"


def test_diagnose_present_in_checkpoint_enrichment_completed() -> None:
    verdict = diagnose_prospect_trace(
        _states(gm_list="found", gm_details="completed", pi_wal="present", checkpoint="present"),
        enrichment=StationResult(station="enrichment", state="completed"),
    )
    assert "enrichment completed" in verdict
    assert categorize_verdict(verdict) == "no gap"


def test_diagnose_present_in_checkpoint_enrichment_never_enqueued() -> None:
    verdict = diagnose_prospect_trace(
        _states(gm_list="found", gm_details="completed", pi_wal="present", checkpoint="present"),
        enrichment=StationResult(station="enrichment", state="never seen"),
    )
    assert "never reached enrichment queue" in verdict
    assert categorize_verdict(verdict) == "Identity Gap (enrichment-enqueue)"


def test_diagnose_present_in_checkpoint_enrichment_pending_or_failed() -> None:
    pending_verdict = diagnose_prospect_trace(
        _states(gm_list="found", gm_details="completed", pi_wal="present", checkpoint="present"),
        enrichment=StationResult(station="enrichment", state="pending"),
    )
    failed_verdict = diagnose_prospect_trace(
        _states(gm_list="found", gm_details="completed", pi_wal="present", checkpoint="present"),
        enrichment=StationResult(station="enrichment", state="failed"),
    )
    assert "enrichment pending" in pending_verdict
    assert "enrichment failed" in failed_verdict
    assert categorize_verdict(failed_verdict) == "Integrity Gap (enrichment failed)"


def test_categorize_verdict_unclassified_falls_back() -> None:
    assert categorize_verdict("something nobody wrote a rule for") == (
        "unclassified - needs manual look"
    )
