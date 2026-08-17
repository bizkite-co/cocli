"""Guards check_and_alert_google_maps_block()'s structured logging.

Previously the only log line produced on a detected block was
send_alert()'s own logger.info("Alert sent to ntfy.sh: ...") on successful
delivery - INFO level, which RollingErrorCounter never sees (it only
listens at ERROR+). A real, successfully-alerted block was therefore
invisible to the heartbeat's rolling error count and cocli audit cluster's
"top error patterns" - only a human watching ntfy would ever know. See
task-agent ticket
regression-gm-list-stuck-at-60-for-months-broken-stealth-script-and-no-backoff-on-google-block-detection.
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cocli.utils.alert_utils import check_and_alert_google_maps_block


def _make_page(url: str = "https://www.google.com/maps/search/x", html: str = "") -> MagicMock:
    page = MagicMock()
    page.url = url
    page.content = AsyncMock(return_value=html)
    return page


@pytest.mark.asyncio
async def test_redirect_block_logs_at_error_level(caplog: pytest.LogCaptureFixture) -> None:
    page = _make_page(url="https://consent.google.com/ml?continue=...")
    with patch("cocli.utils.alert_utils.send_alert", return_value=True):
        with caplog.at_level(logging.ERROR, logger="cocli.utils.alert_utils"):
            detected = await check_and_alert_google_maps_block(page, "test context")

    assert detected is True
    assert any(
        r.levelno >= logging.ERROR and "google_maps_block detected" in r.message
        for r in caplog.records
    )


@pytest.mark.asyncio
async def test_signature_block_logs_at_error_level(caplog: pytest.LogCaptureFixture) -> None:
    page = _make_page(html="<html>Our systems have detected unusual traffic</html>")
    with patch("cocli.utils.alert_utils.send_alert", return_value=True):
        with caplog.at_level(logging.ERROR, logger="cocli.utils.alert_utils"):
            detected = await check_and_alert_google_maps_block(page, "test context")

    assert detected is True
    assert any(
        r.levelno >= logging.ERROR and "google_maps_block detected" in r.message
        for r in caplog.records
    )


@pytest.mark.asyncio
async def test_clean_page_does_not_log_error(caplog: pytest.LogCaptureFixture) -> None:
    page = _make_page(html="<html>Flooring Contractor - 5 stars</html>")
    with caplog.at_level(logging.ERROR, logger="cocli.utils.alert_utils"):
        detected = await check_and_alert_google_maps_block(page, "test context")

    assert detected is False
    assert not any("google_maps_block detected" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_error_is_logged_even_if_ntfy_delivery_fails(caplog: pytest.LogCaptureFixture) -> None:
    """The ERROR log must reflect detection itself, not ntfy delivery success -
    a misconfigured/unreachable ntfy endpoint must not silence this signal."""
    page = _make_page(html="<html>Please try solving the captcha to continue</html>")
    with patch("cocli.utils.alert_utils.send_alert", return_value=False):
        with caplog.at_level(logging.ERROR, logger="cocli.utils.alert_utils"):
            detected = await check_and_alert_google_maps_block(page, "test context")

    assert detected is True
    assert any(
        r.levelno >= logging.ERROR and "google_maps_block detected" in r.message
        for r in caplog.records
    )
