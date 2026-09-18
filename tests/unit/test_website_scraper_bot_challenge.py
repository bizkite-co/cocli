"""_looks_like_bot_challenge() - detects SiteGround's PoW "Robot Challenge
Screen" so the scraper can wait for it to resolve instead of
screenshotting/extracting the challenge shell itself (2026-09-17,
alliedwealth.com investigation)."""

from __future__ import annotations

from unittest.mock import MagicMock

from cocli.enrichment.website_scraper import WebsiteScraper


def _fake_page(url: str) -> MagicMock:
    page = MagicMock()
    page.url = url
    return page


def test_detects_sgcaptcha_url() -> None:
    page = _fake_page("https://alliedwealth.com/.well-known/sgcaptcha/?r=%2F&y=ipc:1.2.3.4:123")
    assert WebsiteScraper._looks_like_bot_challenge(page) is True


def test_detects_fallback_captcha_url() -> None:
    page = _fake_page("https://alliedwealth.com/.well-known/captcha/?y=ipc:1.2.3.4:123&r=%2F")
    assert WebsiteScraper._looks_like_bot_challenge(page) is True


def test_real_page_url_is_not_a_challenge() -> None:
    page = _fake_page("https://alliedwealth.com/about/")
    assert WebsiteScraper._looks_like_bot_challenge(page) is False


def test_bare_root_url_is_not_flagged_by_url_alone() -> None:
    """The bare root is ambiguous by URL alone (it's both the initial
    request AND a possible post-solve bounce-back target) - only the
    .well-known/* paths are unambiguous, so this must return False here;
    the 202-status check in scrape_website_internal is what catches the
    bare-root-still-challenged case."""
    page = _fake_page("https://alliedwealth.com/")
    assert WebsiteScraper._looks_like_bot_challenge(page) is False


def test_empty_url_is_not_a_challenge() -> None:
    page = _fake_page("")
    assert WebsiteScraper._looks_like_bot_challenge(page) is False
