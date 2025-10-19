
import pytest
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock
from pathlib import Path

from cocli.main import app
from cocli.core.config import get_campaigns_dir

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
    
    with patch('cocli.core.config.get_cocli_base_dir', return_value=tmp_path):
        yield campaign_name, campaign_dir / "config.toml"

def test_campaign_edit_with_name(setup_test_campaign):
    campaign_name, config_path = setup_test_campaign
    
    with patch('typer.edit') as mock_edit:
        result = runner.invoke(app, ["campaign", "edit", campaign_name])
        
        assert result.exit_code == 0
        mock_edit.assert_called_once_with(filename=str(config_path))

def test_campaign_edit_with_fzf(setup_test_campaign):
    campaign_name, config_path = setup_test_campaign
    
    with patch('typer.edit') as mock_edit, \
         patch('cocli.commands.campaign.run_fzf', return_value=campaign_name) as mock_fzf:
        result = runner.invoke(app, ["campaign", "edit"])
        
        assert result.exit_code == 0
        mock_fzf.assert_called_once()
        mock_edit.assert_called_once_with(filename=str(config_path))

def test_campaign_edit_no_campaign_selected(setup_test_campaign):
    with patch('cocli.commands.campaign.run_fzf', return_value=None):
        result = runner.invoke(app, ["campaign", "edit"])
        
        assert result.exit_code == 1 # Should exit with a non-zero code
        assert "No campaign selected" in result.stdout

def test_campaign_edit_no_campaigns_exist(tmp_path):
    with patch('cocli.core.config.get_cocli_base_dir', return_value=tmp_path):
        result = runner.invoke(app, ["campaign", "edit"])
        
        assert result.exit_code != 0
        assert "No campaigns found" in result.stdout

def test_campaign_edit_campaign_not_found():
    result = runner.invoke(app, ["campaign", "edit", "non-existent-campaign"])
    
    assert result.exit_code == 1

