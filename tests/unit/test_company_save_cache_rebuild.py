from pathlib import Path
from unittest.mock import patch

import pytest

from cocli.core.paths import paths
from cocli.models.companies.company import Company
from cocli.models.company_name import CompanyName


@pytest.fixture
def sandboxed_companies_dir(tmp_path: Path):
    with patch.object(paths, "root", tmp_path):
        yield paths.companies.path


def test_save_spawns_a_cache_rebuild_thread_by_default(sandboxed_companies_dir: Path) -> None:
    company = Company(name=CompanyName("Acme"), slug="acme")
    with patch("threading.Thread") as mock_thread:
        company.save()
    mock_thread.assert_called_once()


def test_save_does_not_persist_computed_gmb_url(sandboxed_companies_dir: Path) -> None:
    company = Company(
        name=CompanyName("Acme"),
        slug="acme",
        place_id="ChIJQ1A68rPbyYkR_dONAUWyrRo",
        street_address="474 Prospect Blvd",
        city="Frederick",
    )
    company.save(rebuild_cache=False)
    text = (sandboxed_companies_dir / "acme" / "_index.md").read_text()
    assert "gmb_url:" not in text
    assert "query=google" not in text
    assert "query_place_id" in (company.gmb_url or "")
    assert "query=google" not in (company.gmb_url or "")


def test_save_with_rebuild_cache_false_spawns_no_thread(sandboxed_companies_dir: Path) -> None:
    """Regression (Mark, 2026-08-31): a 4,000-item bulk backfill called
    Company.save() once per item with no way to opt out of the per-save
    cache-rebuild thread, spawning ~700 concurrent full-rebuild threads
    before the loop was killed - system load average hit 134. Bulk callers
    must be able to skip the per-item spawn and rebuild once at the end."""
    company = Company(name=CompanyName("Acme"), slug="acme")
    with patch("threading.Thread") as mock_thread:
        company.save(rebuild_cache=False)
    mock_thread.assert_not_called()
