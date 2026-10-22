from datetime import datetime, UTC
from cocli.application.call_history_service import (
    ConnectedCallInfo,
    detect_spoke_in_notes,
    format_call_subject,
    format_call_opener,
)


def test_detect_spoke_in_notes_hashtag():
    is_connected, name = detect_spoke_in_notes("Left brief info #spoke")
    assert is_connected is True
    assert name is None

    is_connected, name = detect_spoke_in_notes("Notes here #connected")
    assert is_connected is True


def test_detect_spoke_in_notes_natural_language():
    is_connected, name = detect_spoke_in_notes("Spoke to Mitch about the Roth conversion tool.")
    assert is_connected is True
    assert name == "Mitch"

    is_connected, name = detect_spoke_in_notes("spoke with him, interested in roadmap")
    assert is_connected is True
    assert name is None

    is_connected, name = detect_spoke_in_notes("Had a call with Tony yesterday.")
    assert is_connected is True
    assert name == "Tony"


def test_detect_spoke_in_notes_negative():
    is_connected, name = detect_spoke_in_notes("Left voicemail, no answer.")
    assert is_connected is False
    assert name is None

    is_connected, name = detect_spoke_in_notes("Gatekeeper said he was not available.")
    assert is_connected is False
    assert name is None


def test_format_call_subject_and_opener():
    call_info = ConnectedCallInfo(
        call_date=datetime(2026, 10, 14, 15, 30, tzinfo=UTC),
        call_date_str="10/14",
        contact_name="Mitch",
        notes_snippet="Spoke to Mitch",
        raw_content="Spoke to Mitch about Roth conversion tool",
    )

    subject = format_call_subject("{first_name}, feedback on The Roadmap", call_info, first_name="Mitch")
    assert "10/14" in subject
    assert "Following up on our talk" in subject

    opener = format_call_opener("Mitch", call_info)
    assert "Hi Mitch," in opener
    assert "10/14" in opener


def test_find_recent_connected_call_mock(monkeypatch):
    from cocli.models.companies.activity import CompanyActivity
    from cocli.application.call_history_service import find_recent_connected_call

    mock_act = [
        CompanyActivity(
            timestamp=datetime(2026, 10, 14, 10, 0, tzinfo=UTC),
            activity_type="call",
            icon="📞",
            title="Call Log: Follow Up Needed",
            preview="Spoke to Mitch about Roth conversion tool",
            content="Spoke to Mitch about Roth conversion tool\n#spoke",
            file_path=None,
        )
    ]

    monkeypatch.setattr(
        "cocli.application.company_service.get_company_activity",
        lambda slug, include_scheduled=False: mock_act,
    )

    result = find_recent_connected_call("higginbotham-financial", contact_name="Mitch Gaylord")
    assert result is not None
    assert result.call_date_str == "10/14"
    assert result.contact_name == "Mitch"

