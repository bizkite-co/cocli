
import pytest

from cocli.tui.app import CocliApp
from cocli.tui.widgets.campaign_selection import CampaignSelection
from conftest import wait_for_widget

@pytest.mark.asyncio
async def test_master_detail_layout(tmp_path, monkeypatch):
    """Test that the master-detail view is laid out horizontally."""
    # Arrange
    monkeypatch.setenv("COCLI_CONFIG_HOME", str(tmp_path))
    (tmp_path / "cocli_config.toml").write_text("""[tui]
master_width = 40
""")

    app = CocliApp()

    async with app.run_test() as driver:
        # Act
        await driver.press("space", "a")
        await wait_for_widget(driver, CampaignSelection)

        # Assert
        assert len(app.query("Horizontal")) == 1
        assert len(app.query("CampaignSelection")) == 1
        assert len(app.query("CampaignDetail")) == 1
        assert app.query_one("#master-pane").styles.width.value == 40
