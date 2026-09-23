from __future__ import annotations

from datetime import datetime, UTC
from pathlib import Path
from unittest.mock import MagicMock, patch
from typer.testing import CliRunner

from cocli.application.company_service import find_company_by_phone, get_company_activity
from cocli.application.protocols import NoteProtocol, SmsNoteProtocol
from cocli.application.sms_service import (
    ingest_sms_message,
    sync_twilio_sms,
)
from cocli.commands.calling import app
from cocli.core.paths import paths
from cocli.models.companies.note import Note
from cocli.models.companies.sms_note import SmsNote
from cocli.utils.calling_provider import TwilioBridgeCallingProvider


runner = CliRunner()


def test_sms_note_to_file_and_from_file(tmp_path: Path) -> None:
    now = datetime(2026, 9, 22, 14, 30, 0, tzinfo=UTC)
    note = SmsNote(
        timestamp=now,
        title="SMS Received: (714) 555-1234",
        type="sms",
        direction="inbound",
        from_phone="+17145551234",
        to_phone="+17144514350",
        content="Hi! Can you call me back later?",
        message_sid="SM1234567890abcdef",
        status="received",
    )

    assert isinstance(note, SmsNoteProtocol)
    assert isinstance(note, NoteProtocol)

    saved_path = note.to_file(tmp_path)
    assert saved_path.exists()
    assert "sms-inbound-SM123456" in saved_path.name

    raw_text = saved_path.read_text(encoding="utf-8")
    assert "type: sms" in raw_text
    assert "direction: inbound" in raw_text
    assert "from: '+17145551234'" in raw_text or "from: +17145551234" in raw_text
    assert "message_sid: SM1234567890abcdef" in raw_text
    assert "Hi! Can you call me back later?" in raw_text

    # Loaded directly from SmsNote
    loaded = SmsNote.from_file(saved_path)
    assert loaded is not None
    assert loaded.message_sid == "SM1234567890abcdef"
    assert loaded.from_phone == "+17145551234"
    assert loaded.direction == "inbound"
    assert loaded.content == "Hi! Can you call me back later?"

    # Loaded polymorphically via Note.from_file
    poly = Note.from_file(saved_path)
    assert isinstance(poly, SmsNote)
    assert poly.message_sid == "SM1234567890abcdef"


def test_company_activity_sms(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(paths, "root", tmp_path)
    comp_dir = tmp_path / "companies" / "acme-corp"
    notes_dir = comp_dir / "notes"
    notes_dir.mkdir(parents=True)
    (comp_dir / "_index.md").write_text("name: Acme Corp\nslug: acme-corp\n")

    sms = SmsNote(
        timestamp=datetime(2026, 9, 22, 12, 0, 0, tzinfo=UTC),
        title="SMS: (714) 555-1234",
        direction="inbound",
        from_phone="+17145551234",
        to_phone="+17144514350",
        content="Please text me the estimate.",
        message_sid="SM99998888",
    )
    sms.to_file(notes_dir)

    activities = get_company_activity("acme-corp")
    assert len(activities) == 1
    act = activities[0]
    assert act.activity_type == "sms"
    assert act.icon == "💬"
    assert act.metadata["message_sid"] == "SM99998888"
    assert "[INBOUND]" in act.preview
    assert "Please text me the estimate." in act.content


def test_find_company_by_phone_and_inbox_ingestion(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(paths, "root", tmp_path)
    comp_dir = tmp_path / "companies" / "test-plumbing"
    comp_dir.mkdir(parents=True)
    (comp_dir / "_index.md").write_text(
        "---\nname: Test Plumbing\nslug: test-plumbing\nphone: (949) 555-4321\n---\n"
    )

    # 1. Reverse lookup matches formatted phone
    matched_slug = find_company_by_phone("+19495554321")
    assert matched_slug == "test-plumbing"

    # 2. Ingest message for matched company
    msg_matched = {
        "sid": "SMaaaabbbb11112222",
        "from": "+19495554321",
        "to": "+17144514350",
        "body": "Got your voicemail, we are interested.",
        "date_sent": "Tue, 22 Sep 2026 14:00:00 +0000",
        "direction": "inbound",
        "status": "received",
    }
    path_1, was_matched_1 = ingest_sms_message(msg_matched)
    assert was_matched_1 is True
    assert path_1 is not None
    assert "test-plumbing" in str(path_1)
    assert path_1.exists()

    # Verify idempotency
    dup_path, dup_matched = ingest_sms_message(msg_matched)
    assert dup_path is None  # Skipped!
    assert dup_matched is True

    # 3. Ingest message for unknown number -> goes to sms_inbox
    msg_unmatched = {
        "sid": "SMccccdddd33334444",
        "from": "+13105559999",
        "to": "+17144514350",
        "body": "Wrong number!",
        "date_sent": "Tue, 22 Sep 2026 14:05:00 +0000",
        "direction": "inbound",
        "status": "received",
    }
    path_2, was_matched_2 = ingest_sms_message(msg_unmatched)
    assert was_matched_2 is False
    assert path_2 is not None
    assert "inbox/sms" in str(path_2)
    assert path_2.exists()


def test_sync_twilio_sms_service(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(paths, "root", tmp_path)

    provider = TwilioBridgeCallingProvider(
        account_sid="AC1234567890",
        auth_token="dummy-token",
        caller_id="+17144514350",
        my_phone="+17144967059",
    )

    sample_messages = [
        {
            "sid": "SM0001",
            "from": "+17145550001",
            "to": "+17144514350",
            "body": "Hello from 1",
            "date_sent": "Tue, 22 Sep 2026 15:00:00 +0000",
            "direction": "inbound",
            "status": "received",
        },
        {
            "sid": "SM0002",
            "from": "+17145550002",
            "to": "+17144514350",
            "body": "Hello from 2",
            "date_sent": "Tue, 22 Sep 2026 15:01:00 +0000",
            "direction": "inbound",
            "status": "received",
        },
    ]

    with patch.object(provider, "fetch_messages", return_value=sample_messages):
        res1 = sync_twilio_sms(provider=provider, limit=10)
        assert res1.synced_count == 2
        assert res1.skipped_count == 0

        # Second sync: both should be skipped as duplicates
        res2 = sync_twilio_sms(provider=provider, limit=10)
        assert res2.synced_count == 0
        assert res2.skipped_count == 2


def test_sync_messages_cli_command(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(paths, "root", tmp_path)

    with patch(
        "cocli.application.sms_service.sync_twilio_sms"
    ) as mock_sync:
        mock_result = MagicMock()
        mock_result.errors = []
        mock_result.synced_count = 1
        mock_result.matched_count = 1
        mock_result.unmatched_count = 0
        mock_result.skipped_count = 0
        mock_result.notes_created = [Path("2026-09-22-sms-inbound-SM1234.md")]
        mock_sync.return_value = mock_result

        result = runner.invoke(app, ["sync-messages"])
        assert result.exit_code == 0
        assert "Synced 1 SMS messages" in result.output
        assert "SM1234" in result.output
