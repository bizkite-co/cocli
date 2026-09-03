"""WebsiteScraper captures a viewport screenshot after page.goto, for the
company-detail "front face" preview (see Website.screenshot_bytes / save()).
A failed capture must not fail the whole scrape. An HTTP error page (404)
must still be captured - otherwise E writes website.md with an error and
no PNG, and the TUI used to call that success.
"""

from __future__ import annotations

from datetime import datetime
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
async def test_http_error_still_captures_viewport_screenshot():
    """A 404/parked landing (Adams Insurance → Relation location 404)
    must still write a screenshot. Raising NavigationError before
    page.screenshot() left website.md with an error and no PNG, and
    the TUI reported success because execute() wraps any returned
    Website dump as status=success."""
    scraper = WebsiteScraper()
    mock_context, mock_page, mock_response = _mocked_success_context()
    mock_response.ok = False
    mock_response.status = 404
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
    assert result.error is not None
    assert "404" in result.error
    assert result.http_status == 404


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


@pytest.mark.asyncio
async def test_force_refresh_survives_naive_domain_index_timestamp():
    """TUI E always force_refresh, but we still loaded the domain index and
    subtracted datetime.now(UTC) from a naive updated_at (CSV/DuckDB often
    strips tz). That TypeError was classified as scraper_bug and written as
    a 'site may be down' note — millvalley.bairdwealth.com, 2026-09-03."""
    scraper = WebsiteScraper()
    mock_context, mock_page, _ = _mocked_success_context()
    mock_page.screenshot = AsyncMock(return_value=_FAKE_PNG)
    indexed = MagicMock()
    indexed.updated_at = datetime(2026, 9, 2, 12, 0, 0)  # naive
    indexed.scraper_version = 6

    with patch.object(scraper, "_resolve_canonical_url", AsyncMock(return_value="https://millvalley.bairdwealth.com")), \
         patch.object(scraper, "_scrape_page", AsyncMock()), \
         patch.object(scraper, "_get_sitemap_urls", AsyncMock(return_value=([], None))), \
         patch.object(scraper, "_navigate_and_scrape", AsyncMock()), \
         patch.object(scraper, "_finalize_enrichment", AsyncMock()), \
         patch("cocli.enrichment.website_scraper.WebsiteDomainCsvManager") as mock_domain_mgr, \
         patch("cocli.scrapers.head_scraper.HeadScraper") as mock_head_scraper:
        mock_domain_mgr.return_value.get_by_domain.return_value = indexed
        mock_head_scraper.return_value.fetch_head = AsyncMock(return_value=(None, None))

        result = await scraper.run(
            browser=mock_context,
            domain="millvalley.bairdwealth.com",
            force_refresh=True,
            site_timeout_seconds=5,
        )

    assert result.error is None
    assert result.error_category is None
    mock_page.goto.assert_called()
