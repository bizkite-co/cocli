"""Inject a per-send tracking token into every outbound link pointing
at the product domain - a plain `str.format()` placeholder in the
template source can't carry this, since the GUID is only minted at
actual-send time (one real email = one GUID), while templates are
rendered to a reusable draft well before that (Mark, 2026-10-03: a
bare first name in utm_term is ambiguous - two "Don"s, or no name at
all - and doesn't tell you *which* of several sends to the same person
someone reacted to).

Operates on the already-rendered body/html_body text as a final pass
right before sending, rather than requiring every template to embed a
`{send_guid}` placeholder - new templates get this automatically, and
nothing can forget to add it.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse


def inject_send_guid(text: str, guid: str, domain: str) -> str:
    """Append `t=<guid>` to the query string of every link in `text`
    that points at `domain` (e.g. "https://getretirementtaxanalyzer.com"
    - scheme is stripped internally, so either http/https in the source
    link matches). Handles both a plain query string (`&`) and the
    HTML-entity-escaped form (`&amp;`) a Jinja-rendered <a href="..."> in
    an HTML email body uses, matching whichever separator the URL
    already uses rather than mixing the two. A link with no existing
    query string (e.g. a bare `.../unsubscribe`) gets `?t=<guid>`.
    """
    bare_domain = urlparse(domain if "://" in domain else f"//{domain}").netloc or domain
    pattern = re.compile(
        r"https?://" + re.escape(bare_domain) + r"[^\s\"'<]*"
    )

    def _append_token(match: re.Match[str]) -> str:
        url = match.group(0)
        separator = "&amp;" if "&amp;" in url else "&"
        if "?" in url:
            return f"{url}{separator}t={guid}"
        return f"{url}?t={guid}"

    return pattern.sub(_append_token, text)
