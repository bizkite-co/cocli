from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, UTC
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Optional

from cocli.application.company_service import find_company_by_phone
from cocli.core.paths import paths
from cocli.models.companies.sms_note import SmsNote
from cocli.models.phone import format_us_phone
from cocli.utils.calling_provider import (
    TwilioBridgeCallingProvider,
    get_calling_provider,
    twilio_config,
)

logger = logging.getLogger(__name__)


@dataclass
class SyncSmsResult:
    """Outcome of an SMS sync operation."""

    synced_count: int = 0
    matched_count: int = 0
    unmatched_count: int = 0
    skipped_count: int = 0
    notes_created: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def parse_sms_datetime(dt_val: Any) -> datetime:
    """Parse Twilio message date string into UTC datetime."""
    if isinstance(dt_val, datetime):
        return dt_val.replace(tzinfo=UTC) if dt_val.tzinfo is None else dt_val
    if not dt_val:
        return datetime.now(UTC)
    s = str(dt_val).strip()
    try:
        return parsedate_to_datetime(s)
    except Exception:
        pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(UTC)


def is_sms_ingested(message_sid: str, notes_dir: Path) -> bool:
    """Check if an SMS note with the given message_sid has already been written to notes_dir."""
    if not notes_dir.exists():
        return False
    short_sid = message_sid[:8]
    for note_file in notes_dir.glob("*-sms-*.md"):
        if short_sid in note_file.name:
            return True
    return False


def ingest_sms_message(
    msg: dict[str, Any],
    campaign_name: Optional[str] = None,
) -> tuple[Optional[Path], bool]:
    """
    Ingests a single Twilio message dict into a company's notes directory or the sms_inbox.

    Returns:
        (path_created, was_matched)
        If skipped due to duplicate, returns (None, was_matched)
    """
    sid = str(msg.get("sid") or "")
    if not sid:
        return None, False

    from_phone = str(msg.get("from") or "")
    to_phone = str(msg.get("to") or "")
    body = str(msg.get("body") or "").strip()
    status = str(msg.get("status") or "")
    direction_raw = str(msg.get("direction") or "inbound").lower()
    direction = "outbound" if "out" in direction_raw else "inbound"

    raw_date = msg.get("date_sent") or msg.get("date_created")
    timestamp = parse_sms_datetime(raw_date)

    # 1. Reverse lookup company slug
    target_slug = find_company_by_phone(from_phone, campaign_name=campaign_name)
    was_matched = bool(target_slug)

    formatted_from = format_us_phone(from_phone) or from_phone

    if target_slug:
        dest_dir = paths.companies.entry(target_slug).path / "notes"
        title = (
            f"SMS Received: {formatted_from}"
            if direction == "inbound"
            else f"SMS Sent: {format_us_phone(to_phone) or to_phone}"
        )
    else:
        dest_dir = paths.sms_inbox.ensure()
        title = (
            f"SMS Received (Unmatched): {formatted_from}"
            if direction == "inbound"
            else f"SMS Sent (Unmatched): {format_us_phone(to_phone) or to_phone}"
        )

    # 2. Deduplication check
    if is_sms_ingested(sid, dest_dir):
        logger.debug(f"SMS {sid} already ingested into {dest_dir}. Skipping.")
        return None, was_matched

    # 3. Create and save SmsNote
    sms_note = SmsNote(
        timestamp=timestamp,
        title=title,
        type="sms",
        direction="inbound" if direction == "inbound" else "outbound",
        from_phone=from_phone,
        to_phone=to_phone,
        content=body,
        message_sid=sid,
        status=status or None,
    )
    written_path = sms_note.to_file(dest_dir)
    logger.info(f"Ingested SMS {sid} to {written_path} (matched={was_matched})")
    return written_path, was_matched


def sync_twilio_sms(
    provider: Optional[TwilioBridgeCallingProvider] = None,
    campaign_name: Optional[str] = None,
    limit: int = 50,
) -> SyncSmsResult:
    """
    Polls Twilio REST API for recent incoming SMS messages and ingests them into
    CRM activity timelines (under companies/<slug>/notes/) or the unassigned inbox.
    """
    result = SyncSmsResult()

    if provider is None:
        p = get_calling_provider(campaign_name)
        if isinstance(p, TwilioBridgeCallingProvider):
            provider = p
        else:
            tw_cfg = twilio_config(campaign_name)
            provider = TwilioBridgeCallingProvider(
                account_sid=tw_cfg.get("account_sid"),
                auth_token=tw_cfg.get("auth_token"),
                caller_id=tw_cfg.get("caller_id") or tw_cfg.get("business_number"),
                my_phone=tw_cfg.get("my_phone") or tw_cfg.get("bridge_to"),
                recording_callback_url=tw_cfg.get("recording_callback_url"),
                record=bool(tw_cfg.get("record", True)),
                low_balance_threshold=float(tw_cfg.get("low_balance_threshold", 20.0)),
            )

    if not provider.is_configured():
        not_configured_msg = (
            "Twilio calling provider is not fully configured. "
            "Please configure account_sid, auth_token, and caller_id."
        )
        logger.warning(not_configured_msg)
        result.errors.append(not_configured_msg)
        return result

    messages = provider.fetch_messages(limit=limit)
    if not messages:
        if provider.last_error:
            result.errors.append(provider.last_error)
        return result

    for msg in messages:
        written_path, matched = ingest_sms_message(msg, campaign_name=campaign_name)
        if written_path:
            result.synced_count += 1
            result.notes_created.append(written_path)
            if matched:
                result.matched_count += 1
            else:
                result.unmatched_count += 1
        else:
            result.skipped_count += 1

    return result
