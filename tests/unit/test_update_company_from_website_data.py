"""update_company_from_website_data()'s email_provider merge step - MX-based
ESP classification (2026-09-17), see cocli/utils/email_provider.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from cocli.application.company_service import update_company_from_website_data
from cocli.core.paths import paths
from cocli.models.companies.company import Company
from cocli.models.companies.website import Website


@pytest.fixture
def sandboxed_companies_dir(tmp_path: Path):
    with patch.object(paths, "root", tmp_path):
        companies_dir = paths.companies.path
        companies_dir.mkdir(parents=True, exist_ok=True)
        yield companies_dir


@pytest.mark.asyncio
async def test_prefers_email_domain_over_website_domain(
    sandboxed_companies_dir: Path,
) -> None:
    """A contact using a personal gmail.com address must be classified by
    that address, not by their company's own (possibly mail-hosting-less)
    domain - the exact Jimmy Jean Insurance case that motivated this."""
    company = Company(
        name="Jimmy Jean Insurance",
        slug="jimmy-jean-insurance",
        domain="jimmyjeaninsurance.com",
        email="jjchange26@gmail.com",
    )
    website_data = Website(url="jimmyjeaninsurance.com")

    with patch(
        "cocli.utils.email_provider.detect_email_provider_async"
    ) as mock_detect:
        mock_detect.return_value = "Gmail"
        modified = await update_company_from_website_data(company, website_data)

    mock_detect.assert_called_once_with("gmail.com")
    assert modified is True
    assert company.email_provider == "Gmail"


@pytest.mark.asyncio
async def test_falls_back_to_website_domain_when_no_email(
    sandboxed_companies_dir: Path,
) -> None:
    company = Company(
        name="Acme Co", slug="acme-co", domain="acme.test", email=None
    )
    website_data = Website(url="acme.test")

    with patch(
        "cocli.utils.email_provider.detect_email_provider_async"
    ) as mock_detect:
        mock_detect.return_value = "Google Workspace"
        modified = await update_company_from_website_data(company, website_data)

    mock_detect.assert_called_once_with("acme.test")
    assert modified is True
    assert company.email_provider == "Google Workspace"


@pytest.mark.asyncio
async def test_skips_lookup_when_already_set(sandboxed_companies_dir: Path) -> None:
    """MX providers rarely change - don't re-resolve on every re-enrichment
    pass once known."""
    company = Company(
        name="Acme Co",
        slug="acme-co",
        domain="acme.test",
        email_provider="Microsoft 365",
    )
    website_data = Website(url="acme.test")

    with patch(
        "cocli.utils.email_provider.detect_email_provider_async"
    ) as mock_detect:
        await update_company_from_website_data(company, website_data)

    mock_detect.assert_not_called()
    assert company.email_provider == "Microsoft 365"


@pytest.mark.asyncio
async def test_no_false_modified_flag_when_provider_not_found(
    sandboxed_companies_dir: Path,
) -> None:
    """A failed/empty DNS lookup must not mark the company modified (and
    trigger an unnecessary save/S3 sync) just because a lookup happened."""
    website_data = Website(url="acme.test")
    company = Company(
        name="Acme Co",
        slug="acme-co",
        domain="acme.test",
        website_url=str(website_data.url),
    )

    with patch(
        "cocli.utils.email_provider.detect_email_provider_async"
    ) as mock_detect:
        mock_detect.return_value = None
        modified = await update_company_from_website_data(company, website_data)

    assert modified is False
    assert company.email_provider is None


@pytest.mark.asyncio
async def test_works_even_when_website_scrape_produced_nothing(
    sandboxed_companies_dir: Path,
) -> None:
    """Independent of website scrape success (e.g. a bot-blocked site
    like allied-wealth.com) - email_provider still gets classified since
    it only needs company.domain/email, not any scraped content."""
    company = Company(name="Allied Wealth", slug="allied-wealth", domain="alliedwealth.com")
    website_data = Website(url="alliedwealth.com", http_status=202, title="Robot Challenge Screen")

    with patch(
        "cocli.utils.email_provider.detect_email_provider_async"
    ) as mock_detect:
        mock_detect.return_value = "Google Workspace"
        modified = await update_company_from_website_data(company, website_data)

    assert modified is True
    assert company.email_provider == "Google Workspace"
