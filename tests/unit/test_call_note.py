from pathlib import Path
from cocli.models.companies.call_note import CallNote
from cocli.application.protocols import CallNoteProtocol


def test_call_note_to_file_and_protocol(tmp_path: Path) -> None:
    note = CallNote(
        title="Call Log: Interested",
        disposition="Interested",
        phone="555-123-4567",
        content="Customer interested in demo.",
    )
    assert isinstance(note, CallNoteProtocol)
    saved_path = note.to_file(tmp_path)
    assert saved_path.exists()
    content = saved_path.read_text(encoding="utf-8")
    assert "disposition: Interested" in content
    assert "phone: 555-123-4567" in content
    assert "Customer interested in demo." in content


def test_call_note_connected_metadata(tmp_path: Path) -> None:
    note = CallNote(
        title="Call Log: Spoke",
        disposition="Follow Up Needed",
        phone="555-123-4567",
        content="Spoke to Mitch about Roth conversion tool #spoke",
        connected=True,
        contact_name="Mitch",
    )
    saved_path = note.to_file(tmp_path)
    loaded = CallNote.from_file(saved_path)
    assert loaded is not None
    assert loaded.connected is True
    assert loaded.contact_name == "Mitch"

