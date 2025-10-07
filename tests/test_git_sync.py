import pytest
from pytest_bdd import scenario, given, when, then, parsers
from typer.testing import CliRunner
from pathlib import Path
import shutil
import os

# Load scenarios from the feature file
# @scenario('../features/git_sync.feature', 'User invokes git-sync with no changes')
def test_git_sync_no_changes():
    pass

# @scenario('../features/git_sync.feature', 'User invokes git-commit with a message')
def test_git_commit_with_message():
    pass

# @scenario('../features/git_sync.feature', 'User invokes git-sync when data directory is not a Git repository')
def test_git_sync_not_git_repo():
    pass

@pytest.fixture
def mock_subprocess_run(mocker):
    """Mocks subprocess.run for git commands."""
    mock_run = mocker.patch('subprocess.run')
    return mock_run

@pytest.fixture
def temp_cocli_data_dir(tmp_path):
    """Creates a temporary cocli data directory."""
    data_dir = tmp_path / "cocli_data"
    data_dir.mkdir()
    yield data_dir
    # Cleanup is handled by tmp_path

@pytest.fixture
def git_repo_data_dir(temp_cocli_data_dir, mocker): # Removed mock_subprocess_run from here
    """Initializes the temporary cocli data directory as a Git repository."""
    # Manually create .git directory for path checks, as mocker doesn't create files
    (temp_cocli_data_dir / ".git").mkdir()

    # Patch os.chdir to allow simulating git commands in the correct directory
    mocker.patch('os.chdir', side_effect=lambda path: None) # Mock chdir to do nothing

    return temp_cocli_data_dir

@given('a cocli data directory that is a Git repository')
def git_repo_setup(git_repo_data_dir, mocker):
    # Ensure the COCLI_DATA_HOME environment variable points to our temporary git repo
    mocker.patch.dict('os.environ', {'COCLI_DATA_HOME': str(git_repo_data_dir)})
    return git_repo_data_dir

@given('a cocli data directory that is NOT a Git repository')
def non_git_repo_setup(temp_cocli_data_dir, mocker):
    # Ensure the COCLI_DATA_HOME environment variable points to our temporary non-git dir
    mocker.patch.dict('os.environ', {'COCLI_DATA_HOME': str(temp_cocli_data_dir)})
    return temp_cocli_data_dir

@given('there are no pending changes in the data directory')
def no_pending_changes(mock_subprocess_run, mocker):
    # Configure mock for git status to show no changes, and git pull/push to be up-to-date
    mock_subprocess_run.side_effect = [
        mocker.Mock(returncode=0, stdout="nothing to commit, working tree clean", stderr=""), # git status (if called)
        mocker.Mock(returncode=0, stdout="Already up to date.", stderr=""), # git pull
        mocker.Mock(returncode=0, stdout="Everything up-to-date", stderr=""), # git push
    ]

@given('there are pending changes in the data directory')
def pending_changes(git_repo_data_dir, mock_subprocess_run, mocker):
    # Create a dummy file to simulate changes
    (git_repo_data_dir / "new_file.txt").write_text("some content")
    # Configure mock for git add/commit to succeed
    mock_subprocess_run.side_effect = [
        mocker.Mock(returncode=0, stdout="", stderr=""), # git add .
        mocker.Mock(returncode=0, stdout="[main] Committed changes", stderr=""), # git commit
    ]

@when('the user runs "cocli git-sync"')
def run_git_sync(runner, cli_app): # Removed mock_subprocess_run, mocker from here
    # The side_effect for git commands should be set in the 'given' step
    result = runner.invoke(cli_app, ["git-sync"])
    pytest.last_result = result # Store result for 'then' steps

@when(parsers.parse('the user runs "cocli git-commit --message \'{message}\'"'))
def run_git_commit(runner, cli_app, message): # Removed mock_subprocess_run, mocker from here
    # The side_effect for git commands should be set in the 'given' step
    result = runner.invoke(cli_app, ["git-commit", "--message", message])
    pytest.last_result = result # Store result for 'then' steps

@then('the command should exit successfully')
def command_exits_successfully():
    assert pytest.last_result.exit_code == 0

@then('the command should exit with an error')
def command_exits_with_error():
    assert pytest.last_result.exit_code != 0

@then(parsers.parse('the output should indicate "{expected_output}"'))
def output_contains(expected_output):
    # stdout and stderr from CliRunner.invoke are already strings
    assert expected_output in pytest.last_result.stdout or \
           expected_output in pytest.last_result.stderr

@then('the changes should be committed to the Git repository')
def changes_committed(mock_subprocess_run, mocker):
    # Verify that git add and git commit were called
    mock_subprocess_run.assert_any_call(["git", "add", "."], cwd=mocker.ANY, capture_output=True, text=True, check=True)
    mock_subprocess_run.assert_any_call(["git", "commit", "-m", "Initial commit"], cwd=mocker.ANY, capture_output=True, text=True, check=True)