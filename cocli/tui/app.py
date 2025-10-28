import toml
import logging

from textual.app import App
from textual.binding import Binding
from textual.widgets import ListView

from .screens.main_menu import MainMenu
from .screens.campaign_selection import CampaignSelection
from ..models.campaign import Campaign
from ..core.config import get_campaign_dir
from .campaign_app import CampaignScreen # Changed from CampaignApp to CampaignScreen

logger = logging.getLogger(__name__)

class CocliApp(App[None]):
    """A Textual app to manage cocli."""

    dark: bool = False

    BINDINGS = [
        Binding("d", "toggle_dark", "Toggle dark mode"),
        Binding("q", "quit", "Quit", show=True),
    ]

    def on_mount(self) -> None:
        self.push_screen(MainMenu())

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item.id == "campaigns":
            self.push_screen(CampaignSelection())
        elif event.item.id == "exit":
            self.exit()

    def on_campaign_selection_selected(self, event: ListView.Selected) -> None:
        campaign_name = event.item.id
        assert campaign_name is not None # Added assert for mypy
        self.pop_screen() # Pop the selection screen

        campaign_dir = get_campaign_dir(campaign_name)
        if not campaign_dir:
            self.notify(f"Campaign '{campaign_name}' not found.", severity="error")
            return

        config_path = campaign_dir / "config.toml"
        if not config_path.exists():
            self.notify(f"Configuration file not found for campaign '{campaign_name}'.", severity="error")
            return

        with open(config_path, "r") as f:
            config_data = toml.load(f)
        
        flat_config = config_data.pop('campaign')
        flat_config.update(config_data)

        try:
            campaign = Campaign.model_validate(flat_config)
        except Exception as e:
            self.notify(f"Error validating campaign configuration for '{campaign_name}': {e}", severity="error")
            return

        self.push_screen(CampaignScreen(campaign=campaign)) # Changed from CampaignApp to CampaignScreen

    def action_toggle_dark(self) -> None:
        """An action to toggle dark mode."""
        self.dark = not self.dark

if __name__ == "__main__":
    app = CocliApp()
    app.run()
