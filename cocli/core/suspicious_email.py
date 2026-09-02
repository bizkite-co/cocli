"""Flag scraped addresses that are placeholders or anti-scrape obfuscation.

``email@example.com`` is RFC 2606. ``bssvpr@fhzzreftvyypcn.pbz`` is ROT13 of
``office@summersgillspa.com`` (``.pbz`` = ``.com``). Those are not inboxes
we should offer to send to; they are scraper-training signal.
"""

from __future__ import annotations

from typing import Optional

from .text_utils import is_valid_email

REASON_PLACEHOLDER = "placeholder-domain"
REASON_ROT13 = "rot13-obfuscation"

_PLACEHOLDER_HOSTS = {
    "example.com",
    "example.net",
    "example.org",
    "example.edu",
    "localhost",
    "invalid",
    "test",
    "email.example",
    "domain.com",
    "yourdomain.com",
    "yourdomain.net",
    "yoursite.com",
}

_PLACEHOLDER_LOCAL = {
    "email",
    "user",
    "username",
    "yourname",
    "firstname",
    "lastname",
    "name",
    "youremail",
}

# rot13("com") = "pbz", etc.
_ROT13_TLDS = {"pbz": "com", "arg": "net", "bet": "org", "rqh": "edu", "tbi": "gov"}

_ROT13_TABLE = str.maketrans(
    "abcdefghijklmnopqrstuvwxyz",
    "nopqrstuvwxyzabcdefghijklm",
)


def rot13(text: str) -> str:
    return text.translate(_ROT13_TABLE)


def classify_scraped_email(email: str) -> Optional[str]:
    """Return a reason code if this should not be treated as a real inbox."""
    raw = (email or "").strip().lower()
    if not raw or "@" not in raw:
        return None
    local, _, host = raw.rpartition("@")
    if not local or not host:
        return None

    if host in _PLACEHOLDER_HOSTS or host.endswith(".example.com"):
        return REASON_PLACEHOLDER
    if host.endswith(".localhost") or host.endswith(".invalid") or host.endswith(".test"):
        return REASON_PLACEHOLDER
    if local in _PLACEHOLDER_LOCAL and host in {
        "example.com",
        "domain.com",
        "email.com",
        "company.com",
        "site.com",
    }:
        return REASON_PLACEHOLDER

    tld = host.rsplit(".", 1)[-1]
    if tld in _ROT13_TLDS:
        return REASON_ROT13
    decoded = rot13(raw)
    if decoded != raw and is_valid_email(decoded):
        decoded_tld = decoded.rsplit(".", 1)[-1]
        if decoded_tld in {"com", "net", "org", "edu", "gov"}:
            return REASON_ROT13

    return None


def snippet_around(haystack: str, needle: str, width: int = 80) -> str:
    if not haystack or not needle:
        return ""
    idx = haystack.lower().find(needle.lower())
    if idx < 0:
        return ""
    start = max(0, idx - width)
    end = min(len(haystack), idx + len(needle) + width)
    return " ".join(haystack[start:end].split())
