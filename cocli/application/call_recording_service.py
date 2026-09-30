from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from cocli.application.company_service import find_company_by_phone
from cocli.application.sms_service import parse_sms_datetime
from cocli.core.paths import paths
from cocli.models.companies.call_note import CallNote
from cocli.models.companies.note import Note
from cocli.models.phone import format_us_phone
from cocli.utils.calling_provider import (
    TwilioBridgeCallingProvider,
    get_calling_provider,
    twilio_config,
)

logger = logging.getLogger(__name__)


def save_transcript_activity_note(
    notes_dir: Path,
    call_timestamp: datetime,
    phone: str,
    transcript_text: str,
) -> Path:
    """Writes the transcript as its own Activity entry, timestamped just
    after the call so it sorts immediately adjacent to the "Call Recording"
    row regardless of when transcription actually ran."""
    formatted_phone = format_us_phone(phone) or phone or "Unknown"
    note = Note(
        timestamp=call_timestamp + timedelta(seconds=1),
        title=f"Transcript: {formatted_phone}",
        content=transcript_text,
    )
    return note.to_file(notes_dir)


@dataclass
class SyncRecordingsResult:
    """Outcome of a call-recording sync operation."""

    synced_count: int = 0
    matched_count: int = 0
    unmatched_count: int = 0
    skipped_count: int = 0
    notes_created: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def is_recording_ingested(recording_sid: str, notes_dir: Path) -> bool:
    """Check whether a CallNote for this recording_sid already exists in notes_dir."""
    if not notes_dir.exists():
        return False
    for note_file in notes_dir.glob("*-call-*.md"):
        try:
            if f"recording_sid: {recording_sid}" in note_file.read_text(encoding="utf-8"):
                return True
        except OSError:
            continue
    return False


def _resolve_provider(
    provider: Optional[TwilioBridgeCallingProvider],
    campaign_name: Optional[str],
) -> TwilioBridgeCallingProvider:
    if provider is not None:
        return provider
    p = get_calling_provider(campaign_name)
    if isinstance(p, TwilioBridgeCallingProvider):
        return p
    tw_cfg = twilio_config(campaign_name)
    return TwilioBridgeCallingProvider(
        account_sid=tw_cfg.get("account_sid"),
        auth_token=tw_cfg.get("auth_token"),
        api_key=tw_cfg.get("api_key"),
        api_secret=tw_cfg.get("api_secret"),
        caller_id=tw_cfg.get("caller_id") or tw_cfg.get("business_number"),
        my_phone=tw_cfg.get("my_phone") or tw_cfg.get("bridge_to"),
        recording_callback_url=tw_cfg.get("recording_callback_url"),
        record=bool(tw_cfg.get("record", True)),
        low_balance_threshold=float(tw_cfg.get("low_balance_threshold", 20.0)),
    )


def _prospect_leg_phone(
    provider: TwilioBridgeCallingProvider, parent_call_sid: str
) -> Optional[str]:
    """Find the phone number of the child ("prospect") leg of a bridged call.

    This bridge provider dials the operator's own phone first (the parent
    call), then <Dial>s the prospect as a child leg - so the parent call's
    `to` is always the operator's own number, never the prospect's. The
    recording attaches to the parent leg, so we have to walk to the child
    leg to find out who was actually recorded.
    """
    children = provider.fetch_calls(parent_call_sid=parent_call_sid)
    for child in children:
        to_phone = child.get("to")
        if to_phone:
            return str(to_phone)
    return None


def sync_twilio_recordings(
    provider: Optional[TwilioBridgeCallingProvider] = None,
    campaign_name: Optional[str] = None,
    limit: int = 50,
) -> SyncRecordingsResult:
    """
    Polls Twilio for recent call recordings, downloads new ones into the
    matching company's `recordings/` directory, and writes a CallNote
    (under `notes/`) so the recording surfaces in the Activity timeline.

    Recordings for companies we can't match by phone are skipped (not
    downloaded) since there is nowhere well-defined to file them.
    """
    result = SyncRecordingsResult()
    resolved_provider = _resolve_provider(provider, campaign_name)

    if not resolved_provider.is_configured():
        msg = (
            "Twilio calling provider is not fully configured. "
            "Please configure account_sid, auth_token, and caller_id."
        )
        logger.warning(msg)
        result.errors.append(msg)
        return result

    calls = resolved_provider.fetch_calls(limit=limit)
    if not calls:
        if resolved_provider.last_error:
            result.errors.append(resolved_provider.last_error)
        return result

    # Recordings attach to the parent (bridge-to-operator) leg only.
    parent_calls = [c for c in calls if not c.get("parent_call_sid")]

    for call in parent_calls:
        parent_sid = str(call.get("sid") or "")
        if not parent_sid:
            continue

        recordings = resolved_provider.fetch_recordings(call_sid=parent_sid)
        if not recordings:
            continue

        prospect_phone = _prospect_leg_phone(resolved_provider, parent_sid)
        target_slug = (
            find_company_by_phone(prospect_phone, campaign_name=campaign_name)
            if prospect_phone
            else None
        )

        if not target_slug:
            result.unmatched_count += len(recordings)
            logger.info(
                "Skipping %d recording(s) for call %s - no company matched for %s",
                len(recordings),
                parent_sid,
                prospect_phone or "(unknown number)",
            )
            continue

        company_dir = paths.companies.entry(target_slug).path
        notes_dir = company_dir / "notes"
        recordings_dir = company_dir / "recordings"

        for rec in recordings:
            recording_sid = str(rec.get("sid") or "")
            if not recording_sid:
                continue

            if is_recording_ingested(recording_sid, notes_dir):
                result.skipped_count += 1
                continue

            dest_path = recordings_dir / f"{recording_sid}.wav"
            if not dest_path.exists():
                ok = resolved_provider.download_recording(recording_sid, dest_path)
                if not ok:
                    if resolved_provider.last_error:
                        result.errors.append(resolved_provider.last_error)
                    continue

            duration_raw = rec.get("duration")
            try:
                duration_seconds = int(duration_raw) if duration_raw is not None else None
            except (TypeError, ValueError):
                duration_seconds = None

            timestamp = parse_sms_datetime(
                rec.get("date_created") or call.get("start_time")
            )
            formatted_phone = format_us_phone(prospect_phone) or prospect_phone

            call_note = CallNote(
                timestamp=timestamp,
                title=f"Call Recording: {formatted_phone}",
                disposition="Recorded",
                phone=prospect_phone or "",
                content="",
                call_sid=parent_sid,
                recording_sid=recording_sid,
                duration_seconds=duration_seconds,
                recording_path=f"recordings/{recording_sid}.wav",
            )
            written_path = call_note.to_file(notes_dir)

            result.synced_count += 1
            result.matched_count += 1
            result.notes_created.append(written_path)
            logger.info(
                "Synced recording %s for call %s to %s", recording_sid, parent_sid, written_path
            )

    return result
