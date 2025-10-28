import toml
import logging

from textual.app import App
from textual.binding import Binding
from textual.widgets import ListView, Input # Import Input for type hinting

from .screens.main_menu import MainMenu
from .screens.campaign_selection import CampaignSelection
from .screens.company_list import CompanyList
from .screens.person_list import PersonList
from .screens.company_detail import CompanyDetail
from .screens.person_detail import PersonDetail
from .screens.etl_enrichment_menu import EtlEnrichmentMenu
from ..models.campaign import Campaign
from ..core.config import get_campaign_dir, create_default_config_file
from .campaign_app import CampaignScreen

logger = logging.getLogger(__name__)

class CocliApp(App[None]):
    """A Textual app to manage cocli."""

    dark: bool = False

    BINDINGS = [
        Binding("d", "toggle_dark", "Toggle dark mode"),
        Binding("q", "quit", "Quit", show=True),
        Binding("j", "cursor_down", "Down", show=False), # New binding
        Binding("k", "cursor_up", "Up", show=False),     # New binding
        Binding("i", "focus_search_input", "Search", show=False), # New binding
        Binding("escape", "blur_search_input", "Exit Search", show=False), # New binding
    ]

    def on_mount(self) -> None:
        create_default_config_file()
        self.push_screen(MainMenu())

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item.id == "campaigns":
            self.push_screen(CampaignSelection())
        elif event.item.id == "companies":
            self.push_screen(CompanyList())
        elif event.item.id == "people":
            self.push_screen(PersonList())
        elif event.item.id == "etl_enrichment":
            self.push_screen(EtlEnrichmentMenu())
        elif event.item.id == "exit":
            self.exit()

    def on_company_list_company_selected(self, message: CompanyList.CompanySelected) -> None:
        """Handle CompanySelected message from CompanyList."""
        self.push_screen(CompanyDetail(company_slug=message.company_slug))

    def on_person_list_person_selected(self, message: PersonList.PersonSelected) -> None:
        """Handle PersonSelected message from PersonList."""
        self.push_screen(PersonDetail(person_slug=message.person_slug))

    def on_campaign_selection_selected(self, event: ListView.Selected) -> None:
        campaign_name = event.item.id
        assert campaign_name is not None
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

        self.push_screen(CampaignScreen(campaign=campaign))

    def action_toggle_dark(self) -> None:
        """An action to toggle dark mode."""
        self.dark = not self.dark

    def action_cursor_down(self) -> None:
        """Move cursor down in the current ListView."""
        if isinstance(self.screen, (MainMenu, CompanyList, PersonList, EtlEnrichmentMenu)):
            list_view = self.screen.query_one(ListView)
            list_view.action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up in the current ListView."""
        if isinstance(self.screen, (MainMenu, CompanyList, PersonList, EtlEnrichmentMenu)):
            list_view = self.screen.query_one(ListView)
            list_view.action_cursor_up()

    def action_focus_search_input(self) -> None:
        """Focus on the search input if available."""
        if isinstance(self.screen, (CompanyList, PersonList)):
            search_input = self.screen.query_one(Input)
            search_input.focus()

    def action_blur_search_input(self) -> None:
        """Blur the search input if focused."""
        if isinstance(self.screen, (CompanyList, PersonList)):
            search_input = self.screen.query_one(Input)
            search_input.blur()

if __name__ == "__main__":
    app = CocliApp()
    app.run()
