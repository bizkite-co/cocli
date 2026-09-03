"""WebsiteScraper.run(): classifies the failure it caught instead of just
storing a flattened string. See task-agent ticket
structured-error-classification-for-enrichmentscraping-failures."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cocli.core.error_classification import ErrorCategory
from cocli.core.exceptions import NavigationError
from cocli.enrichment.website_scraper import WebsiteScraper


@pytest.mark.asyncio
async def test_run_classifies_navigation_error():
    scraper = WebsiteScraper()
    with patch.object(scraper, "scrape_website_internal", AsyncMock(side_effect=NavigationError("dns fail"))), \
         patch.object(scraper, "_finalize_enrichment", AsyncMock()):
        result = await scraper.run(browser=None, domain="dead-site.example.com", site_timeout_seconds=5)

    assert result.error_category == ErrorCategory.NAVIGATION_FAILED
    assert "dns fail" in (result.error or "")


@pytest.mark.asyncio
async def test_run_classifies_unexpected_exception_as_scraper_bug():
    scraper = WebsiteScraper()
    with patch.object(scraper, "scrape_website_internal", AsyncMock(side_effect=AttributeError("boom"))), \
         patch.object(scraper, "_finalize_enrichment", AsyncMock()):
        result = await scraper.run(browser=None, domain="site.example.com", site_timeout_seconds=5)

    assert result.error_category == ErrorCategory.SCRAPER_BUG


@pytest.mark.asyncio
async def test_run_classifies_timeout():
    scraper = WebsiteScraper()

    async def _hang(*args: object, **kwargs: object) -> None:
        import asyncio
        await asyncio.sleep(10)

    with patch.object(scraper, "scrape_website_internal", _hang), \
         patch.object(scraper, "_finalize_enrichment", AsyncMock()):
        result = await scraper.run(browser=None, domain="slow-site.example.com", site_timeout_seconds=0.01)

    assert result.error_category == ErrorCategory.TIMEOUT


@pytest.mark.asyncio
async def test_scrape_website_internal_preserves_navigation_error_through_outer_catch():
    """Regression test: scrape_website_internal's own outer `except Exception`
    (which wraps unexpected failures into a generic EnrichmentError) must not
    also flatten a NavigationError raised earlier in the same try block - that
    silently turned every dead/blocked site into a SCRAPER_BUG in production
    (all navigation-status failures showed up as [scraper_bug] instead of
    [navigation_failed]) because classify_exception() never saw the original
    NavigationError, only the EnrichmentError it got rewrapped into."""
    scraper = WebsiteScraper()

    mock_response = MagicMock(ok=False, status=403)
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock(return_value=mock_response)
    mock_page.screenshot = AsyncMock(return_value=b"\x89PNG")
    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)

    with patch.object(scraper, "_resolve_canonical_url", AsyncMock(return_value="https://blocked-site.example.com")), \
         patch("cocli.enrichment.website_scraper.WebsiteDomainCsvManager") as mock_domain_mgr, \
         patch("cocli.scrapers.head_scraper.HeadScraper") as mock_head_scraper, \
         patch.object(scraper, "_finalize_enrichment", AsyncMock()):
        mock_domain_mgr.return_value.get_by_domain.return_value = None
        mock_head_scraper.return_value.fetch_head = AsyncMock(return_value=(None, None))

        result = await scraper.run(browser=mock_context, domain="blocked-site.example.com", site_timeout_seconds=5)

    assert result.error_category == ErrorCategory.NAVIGATION_FAILED
    assert "403" in (result.error or "")


@pytest.mark.asyncio
async def test_finalize_skips_s3_for_local_tui() -> None:
    from unittest.mock import MagicMock, patch

    from cocli.models.companies.website import Website

    scraper = WebsiteScraper(processed_by="local-tui")
    website = Website(url="example.com", associated_company_folder="example")
    campaign = MagicMock()
    campaign.name = "roadmap"
    with patch("cocli.enrichment.website_scraper.S3CompanyManager") as mock_s3, patch(
        "cocli.enrichment.website_scraper.DomainIndexManager"
    ) as mock_idx:
        mock_idx.return_value.add_or_update = MagicMock()
        await scraper._finalize_enrichment(website, campaign)
    mock_s3.assert_not_called()


@pytest.mark.asyncio
async def test_local_tui_does_not_open_boto3_for_witness() -> None:
    """After a successful goto, scrape used to get_boto3_session because
    campaign.aws is set. Laptop AWS_PROFILE is 1Password-backed, so E
    prompted every time even though the scrape is local."""
    from unittest.mock import AsyncMock, MagicMock, patch

    scraper = WebsiteScraper(processed_by="local-tui")
    mock_response = MagicMock(ok=True, status=200)
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock(return_value=mock_response)
    mock_page.url = "https://example.com"
    mock_page.content = AsyncMock(return_value="<html></html>")
    mock_page.screenshot = AsyncMock(return_value=b"\x89PNG")
    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    campaign = MagicMock()
    campaign.name = "roadmap"
    campaign.aws = MagicMock()
    campaign.prospecting.queries = []
    campaign.prospecting.keywords = []

    with patch.object(scraper, "_resolve_canonical_url", AsyncMock(return_value="https://example.com")), \
         patch.object(scraper, "_scrape_page", AsyncMock()), \
         patch.object(scraper, "_get_sitemap_urls", AsyncMock(return_value=([], None))), \
         patch.object(scraper, "_navigate_and_scrape", AsyncMock()), \
         patch.object(scraper, "_finalize_enrichment", AsyncMock()), \
         patch("cocli.enrichment.website_scraper.WebsiteDomainCsvManager") as mock_domain_mgr, \
         patch("cocli.scrapers.head_scraper.HeadScraper") as mock_head_scraper, \
         patch("cocli.models.campaigns.raw_witness.RawWebsiteWitness.save", return_value=None), \
         patch("cocli.core.reporting.get_boto3_session") as mock_session:
        mock_domain_mgr.return_value.get_by_domain.return_value = None
        mock_head_scraper.return_value.fetch_head = AsyncMock(return_value=(None, None))
        await scraper.run(
            browser=mock_context,
            domain="example.com",
            campaign=campaign,
            site_timeout_seconds=5,
        )

    mock_session.assert_not_called()
