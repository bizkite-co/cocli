"""UTM link formatting and parameter auto-injection utility for campaign outreach."""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

# Regex matching web URLs (http:// or https://)
URL_REGEX = re.compile(r"https?://[^\s<>\"']+")

DEFAULT_OUTREACH_DOMAIN = "getretirementtaxanalyzer.com"


def append_utm_params(
    text: str,
    campaign: Optional[str] = None,
    company_slug: Optional[str] = None,
    source: str = "email_sequence",
    medium: str = "email",
    content: Optional[str] = None,
    term: Optional[str] = None,
    target_domain: Optional[str] = None,
) -> str:
    """
    Search `text` for URLs and auto-inject UTM tracking parameters into them.
    If `target_domain` is specified, only URLs containing target_domain are modified.
    If target_domain is None, all HTTP/HTTPS URLs get UTM parameters attached.
    """
    if not text:
        return text

    def _replace_url(match: re.Match[str]) -> str:
        raw_url = match.group(0)
        trailing_punct = ""
        while raw_url and raw_url[-1] in (")", "]", "}", ".", ",", ";", "!"):
            trailing_punct = raw_url[-1] + trailing_punct
            raw_url = raw_url[:-1]

        parsed = urlparse(raw_url)
        if target_domain and target_domain.lower() not in parsed.netloc.lower():
            return match.group(0)

        query_params = parse_qs(parsed.query, keep_blank_values=True)
        flat_params: dict[str, str] = {k: v[0] for k, v in query_params.items() if v}

        if "utm_source" not in flat_params:
            flat_params["utm_source"] = source
        if "utm_medium" not in flat_params:
            flat_params["utm_medium"] = medium
        if campaign and "utm_campaign" not in flat_params:
            flat_params["utm_campaign"] = campaign

        utm_content_val = content or company_slug
        if utm_content_val and "utm_content" not in flat_params:
            flat_params["utm_content"] = utm_content_val

        if term and "utm_term" not in flat_params:
            flat_params["utm_term"] = term

        new_query = urlencode(flat_params)
        new_parsed = parsed._replace(query=new_query)
        return urlunparse(new_parsed) + trailing_punct

    return URL_REGEX.sub(_replace_url, text)
