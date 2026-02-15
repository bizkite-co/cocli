from unittest.mock import patch
import subprocess

def test_help_command(runner, cli_app):
    result = runner.invoke(cli_app, ["--help"])
    assert result.exit_code == 0
    assert "Usage" in result.stdout
    assert "Commands" in result.stdout

@patch("subprocess.run")
@patch("pathlib.Path.exists")
def test_sync_command_success(mock_exists, mock_subprocess_run, runner, cli_app):
    # Mock that directories exist
    mock_exists.return_value = True
    mock_subprocess_run.return_value.check_returncode.return_value = None

    # Test running sync for a specific campaign
    result = runner.invoke(cli_app, ["sync", "indexes", "my-campaign"])

    assert result.exit_code == 0
    assert "Sync Complete!" in result.stdout
    
    # We expect 4 calls to aws s3 sync:
    # 1. Shared Index Down
    # 2. Shared Index Up
    # 3. Campaign Index Down
    # 4. Campaign Index Up
    assert mock_subprocess_run.call_count == 4
    
    # Check that AWS CLI was called (simplified check)
    args, _ = mock_subprocess_run.call_args
    assert args[0][0] == "aws"
    assert args[0][1] == "s3"
    assert args[0][2] == "sync"

@patch("subprocess.run")
@patch("pathlib.Path.exists")
def test_sync_command_dry_run(mock_exists, mock_subprocess_run, runner, cli_app):
    mock_exists.return_value = True
    mock_subprocess_run.return_value.check_returncode.return_value = None

    result = runner.invoke(cli_app, ["sync", "indexes", "my-campaign", "--dry-run"])

    assert result.exit_code == 0
    
    # Verify --dryrun flag is passed
    # Check at least one call has it
    found_dryrun = False
    for call in mock_subprocess_run.call_args_list:
        if "--dryrun" in call[0][0]:
            found_dryrun = True
            break
    assert found_dryrun

@patch("subprocess.run")
@patch("pathlib.Path.exists")
def test_sync_command_failure(mock_exists, mock_subprocess_run, runner, cli_app):
    mock_exists.return_value = True
    # Simulate an error on the first call
    mock_subprocess_run.side_effect = subprocess.CalledProcessError(1, ["aws", "s3", "sync"])

    result = runner.invoke(cli_app, ["sync", "indexes", "my-campaign"])

    assert result.exit_code == 1
    assert "Sync Failed" in result.stdout