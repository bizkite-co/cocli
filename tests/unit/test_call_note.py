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
