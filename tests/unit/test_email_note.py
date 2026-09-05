from __future__ import annotations
from pathlib import Path
from datetime import datetime, UTC
from cocli.models.companies.email_note import EmailNote
from cocli.models.companies.note import Note
from cocli.application.protocols import NoteProtocol, EmailNoteProtocol


def test_email_note_to_file_and_from_file(tmp_path: Path) -> None:
    now = datetime(2026, 9, 5, 18, 48, 20, tzinfo=UTC)
    email_note = EmailNote(
        timestamp=now,
        title="Test message #2",
        direction="sent",
        from_address="mark@getretirementtaxanalyzer.com",
        to_addresses=["mark@bizkite.net"],
        date=now,
        message_id="msg-12345",
        content="Test body content goes here.",
    )

    # Verify Protocol compliance
    assert isinstance(email_note, NoteProtocol)
    assert isinstance(email_note, EmailNoteProtocol)

    notes_dir = tmp_path / "notes"
    saved_path = email_note.to_file(notes_dir)

    assert saved_path.exists()
    content_raw = saved_path.read_text(encoding="utf-8")
    assert "type: email" in content_raw
    assert "direction: sent" in content_raw
    assert "from: mark@getretirementtaxanalyzer.com" in content_raw
    assert "title: 'Test message #2'" in content_raw or 'title: "Test message #2"' in content_raw or 'title: Test message #2' in content_raw
    assert "- Direction:" not in content_raw

    # Read back via Note.from_file
    loaded = Note.from_file(saved_path)
    assert loaded is not None
    assert isinstance(loaded, EmailNote)
    assert loaded.title == "Test message #2"
    assert loaded.direction == "sent"
    assert loaded.from_address == "mark@getretirementtaxanalyzer.com"
    assert loaded.to_addresses == ["mark@bizkite.net"]
    assert loaded.message_id == "msg-12345"
    assert loaded.content == "Test body content goes here."


def test_legacy_email_note_migration(tmp_path: Path) -> None:
    legacy_markdown = """---
timestamp: 2026-09-05T18:48:20+00:00Z
title: 'Email sent: Test message #2'
---
- Direction: sent
- From: mark@getretirementtaxanalyzer.com
- To: mark@bizkite.net
- Date: 2026-09-05T18:48:20.344320+00:00
- Message-ID: 011101a072e67459-76f96e6a-4ad7-45d0-8028-96bc92cc146e-000000

Test body content from legacy format
"""
    legacy_file = tmp_path / "legacy_note.md"
    legacy_file.write_text(legacy_markdown, encoding="utf-8")

    loaded = Note.from_file(legacy_file)
    assert loaded is not None
    assert isinstance(loaded, EmailNote)
    assert loaded.title == "Test message #2"
    assert loaded.direction == "sent"
    assert loaded.from_address == "mark@getretirementtaxanalyzer.com"
    assert loaded.to_addresses == ["mark@bizkite.net"]
    assert loaded.message_id == "011101a072e67459-76f96e6a-4ad7-45d0-8028-96bc92cc146e-000000"
    assert loaded.content == "Test body content from legacy format"

    # Resave legacy note into new clean format
    notes_dir = tmp_path / "migrated"
    migrated_path = loaded.to_file(notes_dir)
    migrated_raw = migrated_path.read_text(encoding="utf-8")

    assert "- Direction:" not in migrated_raw
    assert "type: email" in migrated_raw
    assert "direction: sent" in migrated_raw
