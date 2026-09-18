"""Parse follow-up date-times, including 'monday' / 'next week'.

dateparser is already a project dependency (see add_meeting.py). Call-log
fields used to accept only strptime('%Y-%m-%d'), so those phrases failed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

import dateparser
from tzlocal import get_localzone


_EXPLICIT_FORMATS = (
    "%Y-%m-%d",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
)


def parse_follow_up_when(raw: str) -> datetime:
    """Return an aware UTC datetime from a typed follow-up string.

    Accepts ISO dates and natural language ('monday', 'next week',
    'tomorrow at 2pm'). Relative phrases are resolved in the operator's
    local timezone, then stored as UTC. Raises ValueError if unparseable.
    """
    text = raw.strip()
    if not text:
        raise ValueError("empty date")

    for fmt in _EXPLICIT_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    local_tz = get_localzone()
    parsed_opt: Optional[datetime] = dateparser.parse(
        text,
        settings={
            "PREFER_DATES_FROM": "future",
            "RETURN_AS_TIMEZONE_AWARE": True,
            "TIMEZONE": str(local_tz),
            "TO_TIMEZONE": "UTC",
            "RELATIVE_BASE": datetime.now(local_tz),
        },
    )
    if parsed_opt is None:
        raise ValueError(f"unparseable date: {raw}")
    if parsed_opt.tzinfo is None:
        return parsed_opt.replace(tzinfo=UTC)
    return parsed_opt.astimezone(UTC)
