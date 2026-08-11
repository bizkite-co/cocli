"""WebsiteScraper.run(): classifies the failure it caught instead of just
storing a flattened string. See task-agent ticket
structured-error-classification-for-enrichmentscraping-failures."""

from unittest.mock import AsyncMock, patch

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
