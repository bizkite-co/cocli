from cocli.application.call_recording_service import SyncRecordingsResult
from cocli.application.sms_service import SyncSmsResult
from cocli.tui.calling_palette import (
    calling_palette_entries,
    summarize_recording_sync,
    summarize_sms_sync,
)


def test_palette_lists_every_calling_cli_command() -> None:
    names = [entry.name for entry in calling_palette_entries()]
    assert names == [
        "calling set-provider",
        "calling set-app-id",
        "calling set-twilio",
        "calling balance",
        "calling sync-messages",
        "calling sync-recordings",
        "calling inspect-recordings",
        "calling status",
        "calling test",
        "calling test-voice",
        "calling test-sms",
        "calling phone-status",
        "calling set-sms-forwarding",
    ]
    by_name = {entry.name: entry for entry in calling_palette_entries()}
    assert by_name["calling sync-messages"].present == "notify"
    assert by_name["calling test-sms"].confirm
    assert by_name["calling set-twilio"].present == "usage"
    assert "set-twilio" in (by_name["calling set-twilio"].usage or "")


def test_sms_sync_summary_reports_matches_and_errors() -> None:
    empty = summarize_sms_sync(SyncSmsResult())
    assert empty.text == "No incoming SMS messages found on Twilio."
    assert empty.severity == "information"

    skipped = summarize_sms_sync(SyncSmsResult(skipped_count=3))
    assert "already recorded" in skipped.text

    synced = summarize_sms_sync(
        SyncSmsResult(synced_count=2, matched_count=1, unmatched_count=1)
    )
    assert "2 SMS" in synced.text
    assert synced.severity == "information"

    failed = summarize_sms_sync(SyncSmsResult(errors=["Twilio is not configured"]))
    assert failed.severity == "error"
    assert "not configured" in failed.text


def test_recording_sync_summary_keeps_unmatched_visible() -> None:
    result = summarize_recording_sync(
        SyncRecordingsResult(synced_count=1, matched_count=1, unmatched_count=2)
    )
    assert "Synced 1" in result.text
    assert "2 recording" in result.text
    assert result.severity == "information"
