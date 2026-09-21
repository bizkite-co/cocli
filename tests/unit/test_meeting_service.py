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


def test_meeting_service_upcoming_and_recent_meetings(tmp_path):
    paths.root = tmp_path
    companies_dir = paths.companies.ensure()

    company_a_dir = companies_dir / "company-a"
    company_a_dir.mkdir(parents=True)
    meetings_dir = company_a_dir / "meetings"
    meetings_dir.mkdir()

    # Create an upcoming meeting file (set it to year 2099 to guarantee future)
    future_file = meetings_dir / "2099-02-20T1030Z-future-meeting.md"
    future_file.write_text(
        "---\ntimestamp: '2099-02-20T10:30:00Z'\ntitle: 'Future Meeting'\ntype: 'meeting'\n---\nFuture stuff.\n"
    )

    # Create a past meeting file (set it to 10 days ago relative to now)
    import tzlocal
    now = datetime.datetime.now(tzlocal.get_localzone())
    past_date = now - datetime.timedelta(days=10)
    past_date_utc = past_date.astimezone(timezone("UTC"))
    past_date_str = past_date_utc.strftime("%Y-%m-%dT%H%MZ")
    
    past_file = meetings_dir / f"{past_date_str}-past-meeting.md"
    past_file.write_text(
        f"---\ntimestamp: '{past_date_utc.isoformat()}'\ntitle: 'Past Meeting'\ntype: 'meeting'\n---\nPast stuff.\n"
    )

    service = MeetingService(campaign_name="test-campaign")
    
    upcoming = service.get_upcoming_meetings()
    recent = service.get_recent_meetings()

    assert len(upcoming) == 1
    assert upcoming[0].title == "Future Meeting"

    assert len(recent) == 1
    assert recent[0].title == "Past Meeting"


def test_meeting_service_recent_calls_caching_and_write_through(tmp_path):
    import tzlocal
    from cocli.models.companies.meeting import CompanyCall

    paths.root = tmp_path
    companies_dir = paths.companies.ensure()

    company_dir = companies_dir / "test-co"
    meetings_dir = company_dir / "meetings"
    meetings_dir.mkdir(parents=True)

    now = datetime.datetime.now(tzlocal.get_localzone())
    past_date = now - datetime.timedelta(days=2)
    past_date_utc = past_date.astimezone(timezone("UTC"))
    past_date_str = past_date_utc.strftime("%Y-%m-%dT%H%MZ")

    call_file = meetings_dir / f"{past_date_str}-call-1.md"
    call_file.write_text(
        f"---\ntimestamp: '{past_date_utc.isoformat()}'\ntitle: 'Logged Call: Follow Up Needed'\ntype: 'phone-call'\n---\nNotes on call 1\n"
    )

    service = MeetingService(campaign_name="test-campaign")

    # Rebuild cache / first call
    calls = service.get_recent_calls(use_cache=False)
    assert len(calls) == 1
    assert calls[0].company_slug == "test-co"
    assert calls[0].title == "Logged Call: Follow Up Needed"

    # Verify cache file was written
    cache_path = service._cache_path()
    assert cache_path.exists()

    # Cached call returns identical result
    cached_calls = service.get_recent_calls(use_cache=True)
    assert len(cached_calls) == 1
    assert cached_calls[0].title == "Logged Call: Follow Up Needed"

    # Write-through a new call record
    new_time = datetime.datetime.now(timezone("UTC"))
    new_call = CompanyCall(
        datetime_utc=new_time,
        datetime_local=new_time.astimezone(tzlocal.get_localzone()),
        company_name="New Co",
        company_slug="new-co",
        title="Logged Call: Interested",
        content="New call notes",
        file_path=tmp_path / "new_call.md",
    )
    service.record_call_in_cache(new_call)

    # Cached call should now have both calls, with newest first
    updated_calls = service.get_recent_calls(use_cache=True)
    assert len(updated_calls) == 2
    assert updated_calls[0].company_slug == "new-co"
    assert updated_calls[0].title == "Logged Call: Interested"
    assert updated_calls[1].company_slug == "test-co"

