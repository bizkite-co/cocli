import logging
import toml

from textual.app import App
from textual.binding import Binding
from textual.widgets import ListView

from .screens.main_menu import MainMenu
from .screens.campaign_selection import CampaignSelection
from .screens.company_list import CompanyList
from .screens.person_list import PersonList
from .screens.person_detail import PersonDetail
from .screens.etl_enrichment_menu import EtlEnrichmentMenu
from .screens.company_detail import CompanyDetailScreen
from ..application.company_service import get_company_details_for_view
from ..models.campaign import Campaign
from ..core.config import get_campaign_dir, create_default_config_file
from ..core import logging_config
from .campaign_app import CampaignScreen

logger = logging.getLogger(__name__)

class CocliApp(App[None]):
    """A Textual app to manage cocli."""

    dark: bool = False

    BINDINGS = [
        Binding("d", "toggle_dark", "Toggle dark mode"),
        Binding("q", "quit", "Quit", show=True),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("h", "go_back", "Back"),
        Binding("l", "select_item", "Select"),
    ]

    def action_go_back(self) -> None:
        logger.debug("action_go_back called")
        self.pop_screen()

    def action_select_item(self) -> None:
        logger.debug("action_select_item called")
        try:
            self.screen.query_one(ListView).action_select_cursor()
        except Exception as e:
            logger.error(f"Error selecting item: {e}")

    def on_mount(self) -> None:
        create_default_config_file()
        logging_config.setup_file_logging("tui", file_level=logging.DEBUG) # Moved logging setup here
        self.push_screen(MainMenu())

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        logger.debug(f"on_list_view_selected called with item ID: {event.item.id}")
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

    def action_cursor_down(self) -> None:
        """Move cursor down in the current ListView."""
        if isinstance(self.screen, (MainMenu, PersonList, EtlEnrichmentMenu, CompanyList, CampaignSelection)):
            list_view = self.screen.query_one(ListView)
            list_view.action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up in the current ListView."""
        if isinstance(self.screen, (MainMenu, PersonList, EtlEnrichmentMenu, CompanyList, CampaignSelection)):
            list_view = self.screen.query_one(ListView)
            list_view.action_cursor_up()



    def on_person_list_person_selected(self, message: PersonList.PersonSelected) -> None:
        """Handle PersonSelected message from PersonList."""
        logger.debug(f"on_person_list_person_selected called with slug: {message.person_slug}")
        self.push_screen(PersonDetail(person_slug=message.person_slug))

    def on_company_list_company_selected(self, message: CompanyList.CompanySelected) -> None:
        """Handle CompanySelected message from CompanyList."""
        logger.debug(f"on_company_list_company_selected called with slug: {message.company_slug}")
        company_slug = message.company_slug
        company_data = get_company_details_for_view(company_slug)
        if company_data:
            self.push_screen(CompanyDetailScreen(company_data))
        else:
            self.bell()

    def on_campaign_selection_campaign_selected(self, message: CampaignSelection.CampaignSelected) -> None:
        """Handle CampaignSelected message from CampaignSelection screen."""
        logger.debug(f"on_campaign_selection_campaign_selected called with campaign: {message.campaign_name}")
        campaign_name = message.campaign_name
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

    async def on_message(self, message: object) -> None:
        """Log all messages in debug mode."""
        if logger.isEnabledFor(logging.DEBUG):
            # Attempt to get more details from the message object
            message_details = {
                "type": message.__class__.__name__,
                "sender": getattr(message, "sender", "N/A"),
                "control": getattr(message, "control", "N/A"),
                "key": getattr(message, "key", "N/A"),
                "value": getattr(message, "value", "N/A"),
                "event_id": getattr(message, "event_id", "N/A"),
                "name": getattr(message, "name", "N/A"),
                "item_id": getattr(message, "item_id", "N/A"), # For ListView.Selected
                "company_slug": getattr(message, "company_slug", "N/A"), # For CompanySelected
                "campaign_name": getattr(message, "campaign_name", "N/A"), # For CampaignSelected
            }
            logger.debug(f"MESSAGE: {message_details}")


if __name__ == "__main__":
    app = CocliApp()
    app.run()
