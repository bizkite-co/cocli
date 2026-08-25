"""Random-sample review mode for `cocli audit queue validate` with no
tile/phrase/usv-path - lets a reviewer start reviewing without having to
guess which single tile/phrase file to pick (previously the command
required one of those three, forcing a blind choice)."""

import csv
from pathlib import Path

from cocli.application.audit_service import AuditService
from cocli.core.paths import paths
from cocli.models.campaigns.indexes.google_maps_list_item import GoogleMapsListItem


def _write_usv(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\x1f")
        for row in rows:
            writer.writerow(row)


def test_sample_random_gm_list_records_draws_from_all_files(tmp_path: Path) -> None:
    field_names = list(GoogleMapsListItem.model_fields.keys())
    results_dir = tmp_path / "results"
    _write_usv(results_dir / "a" / "file1.usv", [[f"place_{i}", "slug", "Name"] for i in range(5)])
    _write_usv(results_dir / "b" / "file2.usv", [[f"place_{i}", "slug", "Name"] for i in range(5, 10)])

    service = AuditService(campaign_name="test")
    sample = service._sample_random_gm_list_records(results_dir, field_names, 4)

    assert len(sample) == 4
    place_ids = {row[0] for row in sample}
    assert len(place_ids) == 4  # no duplicates drawn


def test_sample_random_gm_list_records_excludes_derived_files(tmp_path: Path) -> None:
    field_names = list(GoogleMapsListItem.model_fields.keys())
    results_dir = tmp_path / "results"
    _write_usv(results_dir / "real.usv", [["place_real", "slug", "Name"]])
    _write_usv(results_dir / "compacted.usv", [["place_fake", "slug", "Name"]])

    service = AuditService(campaign_name="test")
    sample = service._sample_random_gm_list_records(results_dir, field_names, 10)

    assert [row[0] for row in sample] == ["place_real"]


def test_sample_random_gm_list_records_returns_fewer_than_n_when_corpus_smaller(
    tmp_path: Path,
) -> None:
    field_names = list(GoogleMapsListItem.model_fields.keys())
    results_dir = tmp_path / "results"
    _write_usv(results_dir / "small.usv", [["place_a", "slug", "Name"]])

    service = AuditService(campaign_name="test")
    sample = service._sample_random_gm_list_records(results_dir, field_names, 10)

    assert len(sample) == 1


def test_prepare_validate_defaults_to_random_mode_with_no_args(tmp_path: Path) -> None:
    paths.root = tmp_path
    campaign = "test-campaign"
    results_dir = paths.queue(campaign, "gm-list").completed / "results"
    rows = [[f"ChIJplace{i:022d}", f"slug-{i}", f"Name {i}"] for i in range(15)]
    _write_usv(results_dir / "tile" / "phrase.usv", rows)

    service = AuditService(campaign_name=campaign)
    res = service.prepare_validate(campaign=campaign)

    assert res["mode"] == "random"
    assert len(res["records"]) == 10  # default sample size


def test_prepare_validate_random_mode_respects_limit(tmp_path: Path) -> None:
    paths.root = tmp_path
    campaign = "test-campaign-limit"
    results_dir = paths.queue(campaign, "gm-list").completed / "results"
    rows = [[f"ChIJplace{i:022d}", f"slug-{i}", f"Name {i}"] for i in range(15)]
    _write_usv(results_dir / "tile" / "phrase.usv", rows)

    service = AuditService(campaign_name=campaign)
    res = service.prepare_validate(campaign=campaign, limit=3)

    assert len(res["records"]) == 3


def test_prepare_validate_random_mode_raises_when_no_results(tmp_path: Path) -> None:
    paths.root = tmp_path
    campaign = "test-campaign-empty"

    service = AuditService(campaign_name=campaign)
    raised = False
    try:
        service.prepare_validate(campaign=campaign)
    except FileNotFoundError:
        raised = True
    assert raised
