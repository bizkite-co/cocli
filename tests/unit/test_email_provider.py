from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from cocli.utils.email_provider import (
    classify_mx_host,
    detect_email_provider,
    detect_email_provider_async,
)


def test_classify_mx_host_matches_known_patterns() -> None:
    assert classify_mx_host("aspmx.l.google.com.") == "Google Workspace"
    assert classify_mx_host("mail.protection.outlook.com") == "Microsoft 365"
    assert classify_mx_host("smtp.secureserver.net") == "GoDaddy"
    assert classify_mx_host("mx-a.mail.am0.yahoodns.net") == "Yahoo"


def test_classify_mx_host_prefers_specific_pattern_over_generic() -> None:
    """protection.outlook.com must classify as Microsoft 365, not get
    shadowed by a broader/wrong pattern - most-specific-first ordering."""
    assert classify_mx_host("example-org.mail.protection.outlook.com") == "Microsoft 365"


def test_classify_mx_host_returns_none_for_unknown_host() -> None:
    assert classify_mx_host("mx.some-random-hosting-company.example") is None


def test_detect_email_provider_shortcuts_free_webmail_without_dns() -> None:
    """gmail.com etc. resolve directly - no DNS call needed, and the
    label is more precise ("Gmail") than the generic MX-derived
    "Google Workspace" a lookup on gmail.com's own MX would produce."""
    with patch("dns.resolver.resolve") as mock_resolve:
        assert detect_email_provider("gmail.com") == "Gmail"
        assert detect_email_provider("HOTMAIL.COM") == "Outlook.com (personal)"
        mock_resolve.assert_not_called()


class _FakeMxRecord:
    def __init__(self, exchange: str) -> None:
        self.exchange = exchange


def test_detect_email_provider_uses_mx_lookup_for_custom_domains() -> None:
    with patch(
        "dns.resolver.resolve",
        return_value=[_FakeMxRecord("aspmx.l.google.com.")],
    ):
        assert detect_email_provider("getretirementtaxanalyzer.com") == "Google Workspace"


def test_detect_email_provider_returns_none_on_dns_failure() -> None:
    with patch("dns.resolver.resolve", side_effect=Exception("NXDOMAIN")):
        assert detect_email_provider("no-such-domain.invalid") is None


def test_detect_email_provider_returns_none_for_empty_domain() -> None:
    assert detect_email_provider("") is None


@pytest.mark.asyncio
async def test_detect_email_provider_async_uses_asyncresolver(monkeypatch: Any) -> None:
    async def fake_resolve(domain: str, record_type: str, lifetime: int) -> list[_FakeMxRecord]:
        assert domain == "getretirementtaxanalyzer.com"
        assert record_type == "MX"
        return [_FakeMxRecord("mail.protection.outlook.com.")]

    import dns.asyncresolver

    monkeypatch.setattr(dns.asyncresolver, "resolve", fake_resolve)

    result = await detect_email_provider_async("getretirementtaxanalyzer.com")
    assert result == "Microsoft 365"


@pytest.mark.asyncio
async def test_detect_email_provider_async_shortcuts_free_webmail_without_dns(
    monkeypatch: Any,
) -> None:
    called = False

    async def fake_resolve(*args: Any, **kwargs: Any) -> list[_FakeMxRecord]:
        nonlocal called
        called = True
        return []

    import dns.asyncresolver

    monkeypatch.setattr(dns.asyncresolver, "resolve", fake_resolve)

    assert await detect_email_provider_async("gmail.com") == "Gmail"
    assert called is False
