"""Service to detect live phone conversations from call history and format personalized follow-ups."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, UTC, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Patterns indicating a live conversation occurred
_SPOKE_TAG_PATTERN = re.compile(r"#\b(spoke|connected|talked)\b", re.IGNORECASE)
_SPOKE_NAME_PATTERN = re.compile(
    r"\b(?:spoke|talked)\s+(?:to|with)\s+([A-Za-z]+)\b", re.IGNORECASE
)
_SPOKE_PRONOUN_PATTERN = re.compile(
    r"\b(?:spoke|talked)\s+(?:to|with)\s+(?:him|her|them)\b", re.IGNORECASE
)
_HAD_CALL_PATTERN = re.compile(
    r"\b(?:had\s+a\s+(?:call|chat|talk|conversation)\s+with)\s+([A-Za-z]+)\b",
    re.IGNORECASE,
)


@dataclass
class ConnectedCallInfo:
    """Details of a prior live conversation with a contact/company."""

    call_date: datetime
    call_date_str: str  # e.g. "10/14"
    contact_name: Optional[str] = None
    notes_snippet: str = ""
    raw_content: str = ""


def detect_spoke_in_notes(
    content: str, contact_name: Optional[str] = None
) -> tuple[bool, Optional[str]]:
    """Inspects note content for indicators that a direct conversation occurred.

    Returns (is_connected, matched_contact_name).
    """
    if not content:
        return False, None

    # 1. Check for explicit hashtag
    has_tag = bool(_SPOKE_TAG_PATTERN.search(content))

    # 2. Check for name mention
    name: Optional[str] = None
    name_match = _SPOKE_NAME_PATTERN.search(content)
    if name_match:
        candidate = name_match.group(1).capitalize()
        if candidate.lower() not in (
            "him", "her", "them", "someone", "receptionist", "assistant", "gatekeeper", "operator"
        ):
            name = candidate
    if not name:
        had_call = _HAD_CALL_PATTERN.search(content)
        if had_call:
            candidate = had_call.group(1).capitalize()
            if candidate.lower() not in (
                "him", "her", "them", "someone", "receptionist", "assistant", "gatekeeper", "operator"
            ):
                name = candidate

    # 3. Check for pronoun
    has_pronoun = bool(_SPOKE_PRONOUN_PATTERN.search(content))

    if has_tag or name or has_pronoun:
        return True, name

    return False, None

    return False, None


def find_recent_connected_call(
    company_slug: str,
    contact_name: Optional[str] = None,
    recipient_email: Optional[str] = None,
    max_days: int = 60,
) -> Optional[ConnectedCallInfo]:
    """Finds the most recent logged call where a direct conversation occurred with the contact or company."""
    from cocli.application.company_service import get_company_activity

    try:
        activities = get_company_activity(company_slug, include_scheduled=False)
    except Exception as exc:
        logger.warning("find_recent_connected_call: could not fetch activity for %s: %s", company_slug, exc)
        return None

    cutoff = datetime.now(UTC) - timedelta(days=max_days)

    first_name = contact_name.strip().split()[0].lower() if contact_name else None

    for act in activities:
        if act.activity_type != "call":
            continue

        ts = act.timestamp.replace(tzinfo=UTC) if act.timestamp.tzinfo is None else act.timestamp
        if ts < cutoff:
            continue

        # Check metadata
        meta = act.metadata or {}
        is_connected = bool(meta.get("connected"))
        matched_name = meta.get("contact_name")

        content = act.content or ""
        if not is_connected:
            detected, found_name = detect_spoke_in_notes(content, contact_name=contact_name)
            if detected:
                is_connected = True
                matched_name = found_name

        if is_connected:
            # If a specific contact name was mentioned in the note, check compatibility if we have first_name
            if matched_name and first_name:
                if matched_name.lower() != first_name:
                    # Note specifically mentions another person (e.g. "Spoke to Tony", but recipient is Mitch)
                    continue

            # Format call date string: M/D (e.g. "10/14")
            call_date_str = f"{ts.month}/{ts.day}"
            clean_snippet = " ".join(content.replace("\n", " ").split())
            if len(clean_snippet) > 120:
                clean_snippet = clean_snippet[:117] + "..."

            return ConnectedCallInfo(
                call_date=ts,
                call_date_str=call_date_str,
                contact_name=matched_name,
                notes_snippet=clean_snippet,
                raw_content=content,
            )

    return None


def format_call_subject(
    base_subject_template: str,
    call_info: Optional[ConnectedCallInfo],
    first_name: str = "",
) -> str:
    """Formats an authentic conversational subject referencing the prior call if available."""
    if not call_info:
        return base_subject_template

    if "{call_date}" in base_subject_template:
        return base_subject_template.replace("{call_date}", call_info.call_date_str)

    # Use conversational follow-up style without fake "RE:" prefix
    return f"Following up on our talk about The Roadmap ({call_info.call_date_str})"


def format_call_opener(first_name: str, call_info: Optional[ConnectedCallInfo]) -> str:
    """Formats an authentic opening paragraph referencing the call."""
    if not call_info:
        return f"Hi {first_name}," if first_name else "Hi,"

    name_str = f"Hi {first_name}," if first_name else "Hi,"
    return f"{name_str}\n\nFollowing up on our talk on {call_info.call_date_str} regarding The Roadmap app..."
