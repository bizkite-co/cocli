"""WebsiteScraper captures a viewport screenshot right after a successful
page load, for the company-detail "front face" preview (see
cocli/models/companies/website.py's screenshot_bytes field and save()).
A failed capture must not fail the whole scrape - it's a nice-to-have,
not core data.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cocli.enrichment.website_scraper import WebsiteScraper

_FAKE_PNG = b"\x89PNG\r\n\x1a\nfake-screenshot-bytes"


def _mocked_success_context() -> tuple[MagicMock, AsyncMock, AsyncMock]:
    """A context/page pair that navigates successfully, for exercising
    scrape_website_internal's post-goto code (screenshot capture) without
    a real browser."""
    mock_response = MagicMock(ok=True, status=200)
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock(return_value=mock_response)
    mock_page.url = "https://example.com"
    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    return mock_context, mock_page, mock_response


@pytest.mark.asyncio
async def test_successful_navigation_captures_viewport_screenshot():
    scraper = WebsiteScraper()
    mock_context, mock_page, _ = _mocked_success_context()
    mock_page.screenshot = AsyncMock(return_value=_FAKE_PNG)

    with patch.object(scraper, "_resolve_canonical_url", AsyncMock(return_value="https://example.com")), \
         patch.object(scraper, "_scrape_page", AsyncMock()), \
         patch.object(scraper, "_get_sitemap_urls", AsyncMock(return_value=([], None))), \
         patch.object(scraper, "_navigate_and_scrape", AsyncMock()), \
         patch.object(scraper, "_finalize_enrichment", AsyncMock()), \
         patch("cocli.enrichment.website_scraper.WebsiteDomainCsvManager") as mock_domain_mgr, \
         patch("cocli.scrapers.head_scraper.HeadScraper") as mock_head_scraper:
        mock_domain_mgr.return_value.get_by_domain.return_value = None
        mock_head_scraper.return_value.fetch_head = AsyncMock(return_value=(None, None))

        result = await scraper.run(browser=mock_context, domain="example.com", site_timeout_seconds=5)

    mock_page.screenshot.assert_called_once_with(type="png")
    assert result.screenshot_bytes == _FAKE_PNG
    assert result.error is None


@pytest.mark.asyncio
async def test_screenshot_capture_failure_does_not_fail_the_scrape():
    scraper = WebsiteScraper()
    mock_context, mock_page, _ = _mocked_success_context()
    mock_page.screenshot = AsyncMock(side_effect=RuntimeError("viewport not ready"))

    with patch.object(scraper, "_resolve_canonical_url", AsyncMock(return_value="https://example.com")), \
         patch.object(scraper, "_scrape_page", AsyncMock()), \
         patch.object(scraper, "_get_sitemap_urls", AsyncMock(return_value=([], None))), \
         patch.object(scraper, "_navigate_and_scrape", AsyncMock()), \
         patch.object(scraper, "_finalize_enrichment", AsyncMock()), \
         patch("cocli.enrichment.website_scraper.WebsiteDomainCsvManager") as mock_domain_mgr, \
         patch("cocli.scrapers.head_scraper.HeadScraper") as mock_head_scraper:
        mock_domain_mgr.return_value.get_by_domain.return_value = None
        mock_head_scraper.return_value.fetch_head = AsyncMock(return_value=(None, None))

        result = await scraper.run(browser=mock_context, domain="example.com", site_timeout_seconds=5)

    assert result.screenshot_bytes is None
    assert result.error is None, "a screenshot failure must not surface as a scrape error"
