import pytest
from unittest.mock import patch
from pathlib import Path
import subprocess

def test_help_command(runner, cli_app):
    result = runner.invoke(cli_app, ["--help"])
    assert result.exit_code == 0
    assert "Usage" in result.stdout
    assert "Commands" in result.stdout

@patch("subprocess.run")
@patch("pathlib.Path.is_dir")
def test_sync_command_success(mock_is_dir, mock_subprocess_run, runner, cli_app):
    mock_is_dir.return_value = True
    mock_subprocess_run.return_value.check_returncode.return_value = None

    result = runner.invoke(cli_app, ["sync", "--message", "Test sync message"])

    assert result.exit_code == 0
    assert "Git sync and push of 'data' folder completed successfully." in result.stdout
    mock_subprocess_run.assert_any_call(["git", "add", "data"], check=True)
    mock_subprocess_run.assert_any_call(["git", "commit", "-m", "Test sync message"], check=True)
    mock_subprocess_run.assert_any_call(["git", "pull", "--rebase"], check=True)
    mock_subprocess_run.assert_any_call(["git", "push"], check=True)

@patch("subprocess.run")
@patch("pathlib.Path.is_dir")
def test_sync_command_no_data_folder(mock_is_dir, mock_subprocess_run, runner, cli_app):
    mock_is_dir.return_value = False

    result = runner.invoke(cli_app, ["sync", "--message", "Test sync message"])

    assert result.exit_code == 1
    assert "Error: 'data' folder not found. Please ensure you are in the project root directory." in result.stdout
    mock_subprocess_run.assert_not_called()

@patch("subprocess.run")
@patch("pathlib.Path.is_dir")
def test_sync_command_git_add_failure(mock_is_dir, mock_subprocess_run, runner, cli_app):
    mock_is_dir.return_value = True
    mock_subprocess_run.side_effect = [
        subprocess.CalledProcessError(1, "git add"),
        None, None, None
    ]

    result = runner.invoke(cli_app, ["sync", "--message", "Test sync message"])

    assert result.exit_code == 1
    assert "Error staging changes: Command 'git add' returned non-zero exit status 1." in result.stdout
    mock_subprocess_run.assert_any_call(["git", "add", "data"], check=True)
    mock_subprocess_run.call_count == 1

@patch("subprocess.run")
@patch("pathlib.Path.is_dir")
def test_sync_command_git_commit_failure(mock_is_dir, mock_subprocess_run, runner, cli_app):
    mock_is_dir.return_value = True
    mock_subprocess_run.side_effect = [
        None,
        subprocess.CalledProcessError(1, "git commit"),
        None, None
    ]

    result = runner.invoke(cli_app, ["sync", "--message", "Test sync message"])

    assert result.exit_code == 1
    assert "Error committing changes: Command 'git commit' returned non-zero exit status 1." in result.stdout
    mock_subprocess_run.assert_any_call(["git", "add", "data"], check=True)
    mock_subprocess_run.assert_any_call(["git", "commit", "-m", "Test sync message"], check=True)
    mock_subprocess_run.call_count == 2

@patch("subprocess.run")
@patch("pathlib.Path.is_dir")
def test_sync_command_git_pull_failure(mock_is_dir, mock_subprocess_run, runner, cli_app):
    mock_is_dir.return_value = True
    mock_subprocess_run.side_effect = [
        None, None,
        subprocess.CalledProcessError(1, "git pull"),
        None
    ]

    result = runner.invoke(cli_app, ["sync", "--message", "Test sync message"])

    assert result.exit_code == 1
    assert "Error pulling changes: Command 'git pull' returned non-zero exit status 1." in result.stdout
    mock_subprocess_run.assert_any_call(["git", "add", "data"], check=True)
    mock_subprocess_run.assert_any_call(["git", "commit", "-m", "Test sync message"], check=True)
    mock_subprocess_run.assert_any_call(["git", "pull", "--rebase"], check=True)
    mock_subprocess_run.call_count == 3

@patch("subprocess.run")
@patch("pathlib.Path.is_dir")
def test_sync_command_git_push_failure(mock_is_dir, mock_subprocess_run, runner, cli_app):
    mock_is_dir.return_value = True
    mock_subprocess_run.side_effect = [
        None, None, None,
        subprocess.CalledProcessError(1, "git push")
    ]

    result = runner.invoke(cli_app, ["sync", "--message", "Test sync message"])

    assert result.exit_code == 1
    assert "Error pushing changes: Command 'git push' returned non-zero exit status 1." in result.stdout
    mock_subprocess_run.assert_any_call(["git", "add", "data"], check=True)
    mock_subprocess_run.assert_any_call(["git", "commit", "-m", "Test sync message"], check=True)
    mock_subprocess_run.assert_any_call(["git", "pull", "--rebase"], check=True)
    mock_subprocess_run.assert_any_call(["git", "push"], check=True)
    mock_subprocess_run.call_count == 4
