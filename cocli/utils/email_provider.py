"""MX-record-based classification of who hosts a domain's email.

A DNS lookup, not a scrape - works even when the website itself is
unreachable (bot-blocked, down, etc.), and needs no browser/HTTP call at
all. Lets outreach scheduling spread sends across ISPs instead of
concentrating on one (Mark, 2026-09-17: "Can we inspect which email
service provider is providing the email service so we could attempt to
spread them amongst providers?").
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Free/consumer webmail domains, matched directly (no MX lookup needed -
# also gives a more precise label than the generic business-product name
# an MX-only check would produce, since e.g. gmail.com's own MX is
# indistinguishable from a paid Google Workspace domain's).
_FREE_WEBMAIL_DOMAINS: dict[str, str] = {
    "gmail.com": "Gmail",
    "googlemail.com": "Gmail",
    "yahoo.com": "Yahoo Mail",
    "outlook.com": "Outlook.com (personal)",
    "hotmail.com": "Outlook.com (personal)",
    "live.com": "Outlook.com (personal)",
    "msn.com": "Outlook.com (personal)",
    "icloud.com": "iCloud Mail",
    "me.com": "iCloud Mail",
    "aol.com": "AOL Mail",
}

# Matched as a case-insensitive substring against each MX hostname, in
# order - first match wins. Most-specific patterns first (e.g. Microsoft's
# own protection.outlook.com before the more generic outlook.com) so a
# specific product isn't shadowed by a broader vendor name.
_KNOWN_PROVIDERS: list[tuple[str, str]] = [
    ("protection.outlook.com", "Microsoft 365"),
    ("outlook.com", "Microsoft 365"),
    ("aspmx.l.google.com", "Google Workspace"),
    ("google.com", "Google Workspace"),
    ("secureserver.net", "GoDaddy"),
    ("godaddy.com", "GoDaddy"),
    ("yahoodns.net", "Yahoo"),
    ("zohomail.com", "Zoho Mail"),
    ("zoho.com", "Zoho Mail"),
    ("pphosted.com", "Proofpoint"),
    ("mimecast.com", "Mimecast"),
    ("barracudanetworks.com", "Barracuda"),
    ("messagelabs.com", "Symantec Email Security"),
    ("emailsrvr.com", "Rackspace Email"),
    ("bluehost.com", "Bluehost"),
]


def classify_mx_host(mx_host: str) -> Optional[str]:
    """Match one MX hostname against the known-provider table."""
    host = mx_host.lower().rstrip(".")
    for pattern, provider in _KNOWN_PROVIDERS:
        if pattern in host:
            return provider
    return None


def detect_email_provider(domain: str) -> Optional[str]:
    """Resolve `domain`'s MX records and classify the mail provider.

    Synchronous - blocks on DNS I/O. Use detect_email_provider_async()
    from inside an async context (e.g. the enrichment pipeline) instead
    of calling this directly there.

    Returns None if the domain has no MX records, DNS resolution fails,
    or no known pattern matches any returned host - callers get a real,
    recognized provider name or nothing, never a raw/unrecognized
    hostname guessed at.
    """
    if not domain:
        return None
    free_webmail = _FREE_WEBMAIL_DOMAINS.get(domain.lower().strip())
    if free_webmail:
        return free_webmail
    try:
        import dns.resolver

        answers = dns.resolver.resolve(domain, "MX", lifetime=10)
    except Exception as exc:
        logger.debug("MX lookup failed for %s: %s", domain, exc)
        return None

    return _classify_answers(answers)


async def detect_email_provider_async(domain: str) -> Optional[str]:
    """Async equivalent of detect_email_provider() - a plain blocking DNS
    call inside an async enrichment pipeline would stall every other
    concurrent scrape task for up to the lookup's timeout."""
    if not domain:
        return None
    free_webmail = _FREE_WEBMAIL_DOMAINS.get(domain.lower().strip())
    if free_webmail:
        return free_webmail
    try:
        import dns.asyncresolver

        answers = await dns.asyncresolver.resolve(domain, "MX", lifetime=10)
    except Exception as exc:
        logger.debug("MX lookup failed for %s: %s", domain, exc)
        return None

    return _classify_answers(answers)


def _classify_answers(answers: object) -> Optional[str]:
    # Multiple MX hosts from the same provider is the overwhelmingly
    # common case - checking in the order DNS returned them (rather than
    # sorting by preference) is fine for classification purposes.
    for rdata in answers:  # type: ignore[attr-defined]
        provider = classify_mx_host(str(rdata.exchange))
        if provider:
            return provider
    return None
