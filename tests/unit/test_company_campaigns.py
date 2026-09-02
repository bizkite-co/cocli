from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from cocli.application.company_service import backfill_campaigns_from_tags
from cocli.models.companies.company import Company
from cocli.models.company_name import CompanyName


def test_add_to_campaign_moves_name_off_tags() -> None:
    company = Company(
        name=CompanyName("Acme"),
        slug="acme",
        tags=["roadmap", "backfilled-from-prospects-2026-08-31"],
        campaigns=[],
    )
    company.add_to_campaign("roadmap")
    assert company.campaigns == ["roadmap"]
    assert "roadmap" not in company.tags
    assert "backfilled-from-prospects-2026-08-31" in company.tags
    assert company.belongs_to_campaign("roadmap")


def test_belongs_to_campaign_falls_back_to_tag() -> None:
    company = Company(
        name=CompanyName("Acme"),
        slug="acme",
        tags=["turboship"],
        campaigns=[],
    )
    assert company.belongs_to_campaign("turboship")
    assert not company.belongs_to_campaign("roadmap")


def test_backfill_campaigns_from_tags_dry_run(tmp_path: Path) -> None:
    company = Company(
        name=CompanyName("Acme"),
        slug="acme",
        tags=["roadmap", "other"],
        campaigns=[],
    )
    with patch.object(Company, "get_all", return_value=[company]), patch(
        "cocli.core.config.get_all_campaign_dirs",
        return_value=[Path("roadmap")],
    ):
        result = backfill_campaigns_from_tags(dry_run=True)
    assert result["dry_run"] is True
    assert result["scanned"] == 1
    assert result["companies_updated"] == 1
    assert result["by_campaign"].get("roadmap") == 1
    assert "acme" in result["slugs"]
    assert company.campaigns == ["roadmap"]
    assert "roadmap" not in company.tags
    assert "other" in company.tags
