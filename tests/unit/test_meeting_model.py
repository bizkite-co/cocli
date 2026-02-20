from datetime import datetime, UTC
from cocli.models.companies.meeting import Meeting

def test_meeting_to_file_and_from_file(tmp_path):
    # Arrange
    meetings_dir = tmp_path / "meetings"
    timestamp = datetime(2026, 2, 20, 10, 30, 0, tzinfo=UTC)
    meeting = Meeting(
        timestamp=timestamp,
        title="Test Phone Call",
        type="phone-call",
        content="Discussed project roadmap."
    )

    # Act
    file_path = meeting.to_file(meetings_dir)
    loaded_meeting = Meeting.from_file(file_path)

    # Assert
    assert file_path.exists()
    assert loaded_meeting is not None
    assert loaded_meeting.title == "Test Phone Call"
    assert loaded_meeting.type == "phone-call"
    assert loaded_meeting.content == "Discussed project roadmap."
    assert loaded_meeting.timestamp == timestamp

def test_meeting_from_file_legacy_name(tmp_path):
    # Test loading from a filename without frontmatter
    meetings_dir = tmp_path / "meetings"
    meetings_dir.mkdir()
    meeting_file = meetings_dir / "2026-02-20T1030Z-legacy-meeting.md"
    meeting_file.write_text("Meeting content here.")

    loaded_meeting = Meeting.from_file(meeting_file)

    assert loaded_meeting is not None
    assert loaded_meeting.title == "Legacy Meeting"
    assert loaded_meeting.timestamp.year == 2026
    assert loaded_meeting.type == "meeting" # Default
    assert loaded_meeting.content == "Meeting content here."
