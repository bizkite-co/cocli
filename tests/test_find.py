import pytest
from typer.testing import CliRunner
from cocli.main import app
from pathlib import Path
import datetime
import os
import shutil

# Fixtures from conftest.py are implicitly available if pytest is configured correctly.
# For clarity, we'll assume runner and cli_app are available.

@pytest.fixture
def temp_cocli_data_dir(tmp_path):
    """
    Fixture to create a temporary cocli data directory for testing.
    This simulates the user's data directory.
    """
    data_dir = tmp_path / "cocli_data"
    data_dir.mkdir()
    # Mock the get_companies_dir to point to our temporary directory
    # This requires patching, which is more complex for a simple draft.
    # For now, assume tests will operate within this structure or
    # we'll need to adjust cocli.main.py to allow configurable data dir.
    # For the purpose of this draft, we'll simulate the structure.
    yield data_dir
    # Cleanup is handled by tmp_path fixture

def create_company_data(data_dir: Path, company_name: str, has_index: bool = True,
                        has_tags: bool = True, recent_meetings: int = 0, old_meetings: int = 0,
                        index_content: str = "", tags_content: str = ""):
    """Helper to set up a company directory with specified files."""
    company_path = data_dir / company_name
    company_path.mkdir(parents=True, exist_ok=True)

    if has_index:
        index_file = company_path / "_index.md"
        if not index_content:
            index_content = f"""---
name: {company_name}
type: Test
---
This is the markdown content for {company_name}.
"""
        index_file.write_text(index_content)

    if has_tags:
        tags_file = company_path / "tags.lst"
        if not tags_content:
            tags_content = "test, example"
        tags_file.write_text(tags_content)

    meetings_dir = company_path / "meetings"
    meetings_dir.mkdir(exist_ok=True)

    # Create recent meetings
    for i in range(recent_meetings):
        meeting_date = datetime.date.today() - datetime.timedelta(days=i*10)
        meeting_file = meetings_dir / f"{meeting_date.strftime('%Y-%m-%d')}-meeting-{i+1}.md"
        meeting_file.write_text(f"Meeting content {i+1}")

    # Create old meetings (older than 6 months)
    for i in range(old_meetings):
        meeting_date = datetime.date.today() - datetime.timedelta(days=181 + i*10)
        meeting_file = meetings_dir / f"{meeting_date.strftime('%Y-%m-%d')}-old-meeting-{i+1}.md"
        meeting_file.write_text(f"Old meeting content {i+1}")

# Mock get_companies_dir to point to the temporary directory
@pytest.fixture(autouse=True)
def mock_get_companies_dir(monkeypatch, temp_cocli_data_dir):
    """
    Mocks the get_companies_dir function in cocli.main to use the temporary directory.
    """
    from cocli import main
    monkeypatch.setattr(main, "get_companies_dir", lambda: temp_cocli_data_dir)

def test_find_no_companies(runner: CliRunner, cli_app):
    """
    Scenario: User invokes find with no companies
    """
    result = runner.invoke(cli_app, ["find"])
    assert result.exit_code == 1
    assert "No companies found." in result.stdout

def test_find_single_strong_match(runner: CliRunner, cli_app, temp_cocli_data_dir):
    """
    Scenario: User invokes find with a query that has a single strong match
    """
    create_company_data(temp_cocli_data_dir, "Acme Corp")
    result = runner.invoke(cli_app, ["find", "Acme"])
    assert result.exit_code == 0
    assert "Found best match: Acme Corp" in result.stdout
    assert "--- Company Details ---" in result.stdout
    assert "This is the markdown content for Acme Corp." in result.stdout

def test_find_multiple_strong_matches_select_by_number(runner: CliRunner, cli_app, temp_cocli_data_dir):
    """
    Scenario: User invokes find with a query that has multiple strong matches and selects one by number
    """
    create_company_data(temp_cocli_data_dir, "Acme Corp")
    create_company_data(temp_cocli_data_dir, "Acme Solutions")
    result = runner.invoke(cli_app, ["find", "Acme"], input="1\n") # Select 1 for Acme Corp
    assert result.exit_code == 0
    assert "Multiple strong matches found for 'Acme':" in result.stdout
    assert "1. Acme Corp" in result.stdout
    assert "2. Acme Solutions" in result.stdout
    assert "--- Company Details ---" in result.stdout
    assert "This is the markdown content for Acme Corp." in result.stdout

def test_find_no_query_select_by_number(runner: CliRunner, cli_app, temp_cocli_data_dir):
    """
    Scenario: User invokes find with no query and selects a company by number
    """
    create_company_data(temp_cocli_data_dir, "Acme Corp")
    create_company_data(temp_cocli_data_dir, "Beta Inc")
    result = runner.invoke(cli_app, ["find"], input="2\n") # Select 2 for Beta Inc
    assert result.exit_code == 0
    assert "Available companies:" in result.stdout
    assert "1. Acme Corp" in result.stdout
    assert "2. Beta Inc" in result.stdout
    assert "--- Company Details ---" in result.stdout
    assert "This is the markdown content for Beta Inc." in result.stdout

def test_find_no_query_select_by_name(runner: CliRunner, cli_app, temp_cocli_data_dir):
    """
    Scenario: User invokes find with no query and selects a company by name
    """
    create_company_data(temp_cocli_data_dir, "Acme Corp")
    create_company_data(temp_cocli_data_dir, "Beta Inc")
    result = runner.invoke(cli_app, ["find"], input="Beta Inc\n") # Select Beta Inc by name
    assert result.exit_code == 0
    assert "Available companies:" in result.stdout
    assert "1. Acme Corp" in result.stdout
    assert "2. Beta Inc" in result.stdout
    assert "--- Company Details ---" in result.stdout
    assert "This is the markdown content for Beta Inc." in result.stdout

def test_find_invalid_selection_then_valid(runner: CliRunner, cli_app, temp_cocli_data_dir):
    """
    Scenario: User invokes find with an invalid selection during interactive mode
    """
    create_company_data(temp_cocli_data_dir, "Acme Corp")
    create_company_data(temp_cocli_data_dir, "Beta Inc")
    result = runner.invoke(cli_app, ["find"], input="invalid\n1\n") # Invalid then valid selection
    assert result.exit_code == 0
    assert "Invalid selection. Please try again." in result.stdout
    assert "--- Company Details ---" in result.stdout
    assert "This is the markdown content for Acme Corp." in result.stdout

def test_find_company_full_details(runner: CliRunner, cli_app, temp_cocli_data_dir):
    """
    Scenario: User invokes find for a company with _index.md, tags.lst, and recent meetings
    """
    create_company_data(temp_cocli_data_dir, "Example Corp", recent_meetings=2, old_meetings=1,
                        index_content="---\nname: Example Corp\n---", tags_content="tech, software")
    result = runner.invoke(cli_app, ["find", "Example Corp"])
    assert result.exit_code == 0
    assert "--- Company Details ---" in result.stdout
    assert "--- Tags ---" in result.stdout
    assert "tech, software" in result.stdout
    assert "--- Recent Meetings ---" in result.stdout
    # Check for recent meeting dates (last 2 days)
    today = datetime.date.today()
    for i in range(2):
        meeting_date = today - datetime.timedelta(days=i*10)
        assert meeting_date.strftime('%Y-%m-%d') in result.stdout
    # Ensure old meeting is not displayed
    old_meeting_date = today - datetime.timedelta(days=181)
    assert old_meeting_date.strftime('%Y-%m-%d') not in result.stdout
    assert "To view all meetings: cocli view-meetings Example Corp" in result.stdout
    assert "To add a new meeting: cocli add-meeting Example Corp" in result.stdout

def test_find_company_no_index_md(runner: CliRunner, cli_app, temp_cocli_data_dir):
    """
    Scenario: User invokes find for a company with no _index.md
    """
    create_company_data(temp_cocli_data_dir, "NoIndex Corp", has_index=False)
    result = runner.invoke(cli_app, ["find", "NoIndex Corp"])
    assert result.exit_code == 0
    assert "No _index.md found for NoIndex Corp." in result.stdout

def test_find_company_no_tags_lst(runner: CliRunner, cli_app, temp_cocli_data_dir):
    """
    Scenario: User invokes find for a company with no tags.lst
    """
    create_company_data(temp_cocli_data_dir, "NoTags Corp", has_tags=False)
    result = runner.invoke(cli_app, ["find", "NoTags Corp"])
    assert result.exit_code == 0
    assert "No tags found." in result.stdout

def test_find_company_no_recent_meetings(runner: CliRunner, cli_app, temp_cocli_data_dir):
    """
    Scenario: User invokes find for a company with no recent meetings
    """
    create_company_data(temp_cocli_data_dir, "NoMeetings Corp", recent_meetings=0, old_meetings=2)
    result = runner.invoke(cli_app, ["find", "NoMeetings Corp"])
    assert result.exit_code == 0
    assert "No recent meetings found." in result.stdout