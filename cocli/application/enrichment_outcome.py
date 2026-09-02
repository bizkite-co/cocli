"""Turn an op_re_enrich execute() payload into a TUI notification.

execute() wraps every returned Website dump as ``status: success``, even
when the scrape 404'd. The toast has to read the nested ``error`` /
``http_status`` and not claim success.
"""

from __future__ import annotations

import re
from typing import Any, Literal, Optional


def _unique_email_count(payload: dict[str, Any]) -> int:
    found: set[str] = set()
    for raw in payload.get("all_emails") or []:
        email = str(raw).strip().lower()
        if email:
            found.add(email)
    primary = str(payload.get("email") or "").strip().lower()
    if primary:
        found.add(primary)
    for person in payload.get("personnel") or []:
        if isinstance(person, dict):
            email = str(person.get("email") or "").strip().lower()
            if email:
                found.add(email)
    return len(found)


def http_status_from_payload(payload: dict[str, Any]) -> Optional[int]:
    raw = payload.get("http_status")
    if raw is not None and raw != "":
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    err = str(payload.get("error") or payload.get("message") or "")
    match = re.search(r"\b([45]\d\d|522|523|524|525|526|530)\b", err)
    if match:
        return int(match.group(1))
    return None


def notify_from_execute_result(
    result: dict[str, Any],
) -> tuple[str, Literal["information", "warning", "error"]]:
    """Return ``(message, textual_severity)``.

    HTTP/navigation failures are ``warning`` (orange). Unexpected outer
    execute failures stay ``error``. Success is ``information``.
    """
    inner = result.get("result") if isinstance(result.get("result"), dict) else result
    if not isinstance(inner, dict):
        inner = {}

    err = inner.get("error")
    if not err and inner.get("status") == "error":
        err = inner.get("message") or "No data captured"
    if result.get("status") not in (None, "success") and not err:
        err = result.get("message") or "Enrichment failed"

    if not err:
        n = _unique_email_count(inner)
        return f"Enrichment successful ({n} emails). Refreshing view...", "information"

    status = http_status_from_payload(inner)
    url = inner.get("url") or inner.get("domain") or ""
    category = inner.get("error_category") or ""
    if hasattr(category, "value"):
        category = category.value

    parts = ["Website enrichment failed"]
    if status is not None:
        parts.append(f"HTTP {status}")
    if category:
        parts.append(str(category))
    if url:
        parts.append(str(url))
    parts.append(str(err))
    return " — ".join(parts), "warning"
