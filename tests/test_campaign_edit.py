import pytest
from typer.testing import CliRunner
from unittest.mock import patch

from cocli.main import app

runner = CliRunner()

@pytest.fixture(scope="function")
def setup_test_campaign(tmp_path):
    campaigns_dir = tmp_path / "campaigns"
    campaigns_dir.mkdir()

    campaign_name = "test-campaign"
    campaign_dir = campaigns_dir / campaign_name
    campaign_dir.mkdir()

    config_content = "[campaign]\nname = \"Test Campaign\"\n"
    (campaign_dir / "config.toml").write_text(config_content)

    readme_content = "# Test Campaign\n"
    (campaign_dir / "README.md").write_text(readme_content)

    with patch('cocli.core.config.get_cocli_base_dir', return_value=tmp_path):
        yield campaign_name, campaign_dir

def test_campaign_edit_with_editor_configured(setup_test_campaign):
    campaign_name, campaign_dir = setup_test_campaign
    config_path = campaign_dir / "config.toml"
    readme_path = campaign_dir / "README.md"
    editor_cmd = "my-editor"

    with patch('cocli.commands.campaign.get_editor_command', return_value=editor_cmd) as mock_get_editor, \
         patch('subprocess.run') as mock_subprocess_run:
        result = runner.invoke(app, ["campaign", "edit", campaign_name])

        assert result.exit_code == 0
        mock_subprocess_run.assert_called_once_with([editor_cmd, str(config_path), str(readme_path)])

def test_campaign_edit_with_vim_editor(setup_test_campaign):
    campaign_name, campaign_dir = setup_test_campaign
    config_path = campaign_dir / "config.toml"
    readme_path = campaign_dir / "README.md"
    editor_cmd = "nvim"

    with patch('cocli.commands.campaign.get_editor_command', return_value=editor_cmd) as mock_get_editor, \
         patch('subprocess.run') as mock_subprocess_run:
        result = runner.invoke(app, ["campaign", "edit", campaign_name])

        assert result.exit_code == 0
        mock_get_editor.assert_called_once()
        mock_subprocess_run.assert_called_once_with([editor_cmd, "-o", str(config_path), str(readme_path)])

def test_campaign_edit_no_editor_configured(setup_test_campaign):
    campaign_name, campaign_dir = setup_test_campaign
    config_path = campaign_dir / "config.toml"

    with patch('cocli.commands.campaign.get_editor_command', return_value=None) as mock_get_editor, \
         patch('typer.edit') as mock_typer_edit:
        result = runner.invoke(app, ["campaign", "edit", campaign_name])

        assert result.exit_code == 0
        mock_get_editor.assert_called_once()
        mock_typer_edit.assert_called_once_with(filename=str(config_path))
        assert "To edit the README.md as well, please configure an editor" in result.stdout

def test_campaign_edit_with_fzf(setup_test_campaign):
    campaign_name, campaign_dir = setup_test_campaign
    config_path = campaign_dir / "config.toml"
    readme_path = campaign_dir / "README.md"
    editor_cmd = "my-editor"

    with patch('cocli.commands.campaign.get_editor_command', return_value=editor_cmd), \
         patch('cocli.commands.campaign.run_fzf', return_value=campaign_name) as mock_fzf, \
         patch('subprocess.run') as mock_subprocess_run:
        result = runner.invoke(app, ["campaign", "edit"])

        assert result.exit_code == 0
        mock_fzf.assert_called_once()
        mock_subprocess_run.assert_called_once_with([editor_cmd, str(config_path), str(readme_path)])

def test_campaign_edit_no_campaign_selected(setup_test_campaign):
    with patch('cocli.commands.campaign.run_fzf', return_value=None):
        result = runner.invoke(app, ["campaign", "edit"])

        assert result.exit_code == 1
        assert "No campaign selected" in result.stdout

def test_campaign_edit_no_campaigns_exist(tmp_path):
    with patch('cocli.core.config.get_cocli_base_dir', return_value=tmp_path):
        result = runner.invoke(app, ["campaign", "edit"])

        assert result.exit_code == 1
        assert "No campaigns found" in result.stdout

def test_campaign_edit_campaign_not_found():
    result = runner.invoke(app, ["campaign", "edit", "non-existent-campaign"])

    assert result.exit_code == 1