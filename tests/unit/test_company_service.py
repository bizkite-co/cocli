from pathlib import Path
from unittest.mock import patch

import pytest

from cocli.application.company_service import backfill_missing_companies_from_prospects
from cocli.core.paths import paths
from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
from cocli.models.company_name import CompanyName


def _prospect(slug: str, name: str) -> GoogleMapsProspect:
    return GoogleMapsProspect(
        place_id=f"ChIJ-test-place-id-{slug}-0000000000",
        slug=slug,
        name=CompanyName(name),
        average_rating=4.5,
        reviews_count=10,
        domain=f"{slug}.com",
    )


@pytest.fixture
def sandboxed_companies_dir(tmp_path: Path):
    with patch.object(paths, "root", tmp_path):
        companies_dir = paths.companies.path
        companies_dir.mkdir(parents=True, exist_ok=True)
        yield companies_dir


def test_dry_run_reports_but_does_not_write(sandboxed_companies_dir: Path) -> None:
    with patch(
        "cocli.core.prospects_csv_manager.ProspectsIndexManager.read_all_prospects",
        return_value=[_prospect("missing-co", "Missing Co")],
    ):
        result = backfill_missing_companies_from_prospects("test-campaign", dry_run=True)

    assert result["missing_count"] == 1
    assert result["created_count"] == 0
    assert not (sandboxed_companies_dir / "missing-co").exists()


def test_execute_creates_directory_tagged_with_campaign_and_provenance_marker(
    sandboxed_companies_dir: Path,
) -> None:
    with patch(
        "cocli.core.prospects_csv_manager.ProspectsIndexManager.read_all_prospects",
        return_value=[_prospect("missing-co", "Missing Co")],
    ):
        result = backfill_missing_companies_from_prospects("test-campaign", dry_run=False)

    assert result["created_count"] == 1
    company_dir = sandboxed_companies_dir / "missing-co"
    assert company_dir.exists()
    index_text = (company_dir / "_index.md").read_text()
    assert "test-campaign" in index_text
    assert result["tag"] in index_text


def test_skips_prospects_that_already_have_a_company_directory(
    sandboxed_companies_dir: Path,
) -> None:
    company_dir = sandboxed_companies_dir / "already-here"
    company_dir.mkdir()
    (company_dir / "_index.md").write_text("---\nname: Already Here\n---\n")

    with patch(
        "cocli.core.prospects_csv_manager.ProspectsIndexManager.read_all_prospects",
        return_value=[_prospect("already-here", "Already Here")],
    ):
        result = backfill_missing_companies_from_prospects("test-campaign", dry_run=False)

    assert result["missing_count"] == 0
    assert result["created_count"] == 0


def test_backfills_a_bare_directory_with_no_index_md(
    sandboxed_companies_dir: Path,
) -> None:
    """Regression (Mark, 2026-08-31): the enrichment worker's
    Website.save() creates companies/<slug>/enrichments/ via
    mkdir(parents=True) for slugs with no company yet, leaving a bare
    directory with no _index.md (126 found in production). That's not a
    real company record - Company.from_directory() treats it the same as
    missing - so it must not be skipped as "already exists"."""
    shell_dir = sandboxed_companies_dir / "enrichment-shell-only"
    (shell_dir / "enrichments").mkdir(parents=True)
    (shell_dir / "enrichments" / "website.md").write_text("---\ndomain: shell.com\n---\n")

    with patch(
        "cocli.core.prospects_csv_manager.ProspectsIndexManager.read_all_prospects",
        return_value=[_prospect("enrichment-shell-only", "Enrichment Shell Only")],
    ):
        result = backfill_missing_companies_from_prospects("test-campaign", dry_run=False)

    assert result["created_count"] == 1
    assert (shell_dir / "_index.md").exists()
