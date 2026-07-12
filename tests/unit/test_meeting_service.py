import datetime
from pytz import timezone

from cocli.core.paths import paths
from cocli.application.meeting_service import MeetingService
from cocli.models.companies.meeting import CompanyMeeting


def test_meeting_service_gathers_meetings(tmp_path):
    # Arrange: isolate paths and set up mock company and meeting files
    paths.root = tmp_path
    companies_dir = paths.companies.ensure()

    # Create mock company directories
    company_a_dir = companies_dir / "company-a"
    company_a_dir.mkdir(parents=True)
    meetings_dir = company_a_dir / "meetings"
    meetings_dir.mkdir()

    # Create a meeting file
    meeting_file = meetings_dir / "2026-02-20T1030Z-discuss-roadmap.md"
    meeting_file.write_text(
        "---\ntimestamp: '2026-02-20T10:30:00Z'\ntitle: 'Roadmap Discussion'\ntype: 'meeting'\n---\nWe discussed details.\n"
    )

    # Act
    service = MeetingService(campaign_name="test-campaign")
    meetings = service.get_all_meetings()

    # Assert
    assert len(meetings) == 1
    m = meetings[0]
    assert isinstance(m, CompanyMeeting)
    assert m.company_name == "Company A"
    assert m.title == "Roadmap Discussion"
    assert m.datetime_utc == datetime.datetime(
        2026, 2, 20, 10, 30, tzinfo=timezone("UTC")
    )
    assert m.file_path == meeting_file
