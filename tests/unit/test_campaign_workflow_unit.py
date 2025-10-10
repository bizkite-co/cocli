import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from cocli.core.campaign_workflow import CampaignWorkflow
from cocli.commands.campaign import next_step as campaign_next_step

class TestCampaignWorkflow:
    @pytest.fixture
    def workflow(self):
        with patch('cocli.core.campaign_workflow.CampaignWorkflow._get_campaign_config_path') as mock_get_config_path:
            mock_get_config_path.return_value = Path("campaigns/test_campaign/config.toml")
            with patch.object(Path, 'exists', return_value=True):
                with patch('toml.load', return_value={"campaign": {"current_state": "idle"}}):
                    with patch('toml.dump'):
                        instance = CampaignWorkflow(name="test_campaign")
                        instance.machine.set_state(instance.state)
                        return instance

    def test_transition_to_prospecting_enriching(self, workflow):
        workflow.machine.set_state("prospecting_importing")
        workflow.finish_prospecting_import()
        assert workflow.state == "prospecting_enriching"

    def test_transition_from_prospecting_enriching_to_outreach(self, workflow):
        workflow.machine.set_state("prospecting_enriching")
        workflow.finish_enriching()
        assert workflow.state == "outreach"

class TestCampaignCommands:
    @pytest.fixture
    def mock_campaign_workflow(self):
        with patch('cocli.commands.campaign.CampaignWorkflow') as MockCampaignWorkflow:
            mock_instance = MagicMock(spec=CampaignWorkflow)
            mock_instance.state = "prospecting_enriching" # Initial state for the mock

            # Explicitly add the finish_enriching method to the mock
            mock_instance.finish_enriching = MagicMock()

            def mock_finish_enriching():
                mock_instance.state = "outreach" # Simulate state change
            mock_instance.finish_enriching.side_effect = mock_finish_enriching
            MockCampaignWorkflow.return_value = mock_instance
            yield mock_instance

    def test_next_step_calls_finish_enriching(self, mock_campaign_workflow):
        campaign_next_step(campaign_name="test_campaign")
        mock_campaign_workflow.finish_enriching.assert_called_once()
        assert mock_campaign_workflow.state == "outreach"
