import logging
import toml

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Static, ListView
from textual.containers import Container
from textual import events # Import events for on_key


from .widgets.campaign_selection import CampaignSelection
from .widgets.company_list import CompanyList
from .widgets.person_list import PersonList
from .widgets.person_detail import PersonDetail
from .widgets.prospect_menu import ProspectMenu
from .widgets.company_detail import CompanyDetail
from ..application.company_service import get_company_details_for_view
from ..models.campaign import Campaign
from ..core.config import get_campaign_dir, create_default_config_file
from ..core import logging_config
from .campaign_app import CampaignScreen

logger = logging.getLogger(__name__)

class CocliApp(App[None]):
    """A Textual app to manage cocli."""

    dark: bool = False
    CSS_PATH = "tui.css"
    
    CSS_PATH = "tui.css" 
    BINDINGS = [
        Binding("d", "toggle_dark", "Toggle dark mode"),
        Binding("q", "quit", "Quit", show=True),
        Binding("alt+shift+c", "show_campaigns", "Campaigns", show=True),
        Binding("alt+shift+p", "show_people", "People", show=True),
        Binding("alt+c", "show_companies", "Companies", show=True),
        Binding("alt+p", "show_prospects", "Prospect", show=True),
        Binding("l", "select_item", "Select", show=False),
    ]

    async def on_key(self, event: events.Key) -> None:
        logger.debug(f"Key pressed: {event.key}")


        




    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        yield Static("[b]Campaigns[/b] (Alt+Shift+C) | [b]People[/b] (Alt+Shift+P) | [b]Companies[/b] (Alt+C) | [b]Prospect[/b] (Alt+P)", id="menu_bar")
        yield Container(id="app_content")

    def on_mount(self) -> None:
        create_default_config_file()
        logging_config.setup_file_logging("tui", file_level=logging.DEBUG) # Moved logging setup here








    def on_person_list_person_selected(self, message: PersonList.PersonSelected) -> None:
        """Handle PersonSelected message from PersonList."""
        logger.debug(f"on_person_list_person_selected called with slug: {message.person_slug}")
        self.query_one("#app_content").remove_children()
        self.query_one("#app_content").mount(PersonDetail(person_slug=message.person_slug))

    def on_company_list_company_selected(self, message: CompanyList.CompanySelected) -> None:
        """Handle CompanySelected message from CompanyList."""
        logger.debug(f"on_company_list_company_selected called with slug: {message.company_slug}")
        company_slug = message.company_slug
        company_data = get_company_details_for_view(company_slug)
        if company_data:
            self.query_one("#app_content").remove_children()
            company_detail = CompanyDetail(company_data)
            self.query_one("#app_content").mount(company_detail)
            company_detail.styles.display = "block"
        else:
            self.bell()

    def on_campaign_selection_campaign_selected(self, message: CampaignSelection.CampaignSelected) -> None:
        """Handle CampaignSelected message from CampaignSelection screen."""
        logger.debug(f"on_campaign_selection_campaign_selected called with campaign: {message.campaign_name}")
        campaign_name = message.campaign_name
        assert campaign_name is not None

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

        self.query_one("#app_content").remove_children()
        self.query_one("#app_content").mount(CampaignScreen(campaign=campaign))

    def action_show_campaigns(self) -> None:
        """Show the campaigns selection screen."""
        self.query_one("#app_content").remove_children()
        campaign_selection = CampaignSelection()
        self.query_one("#app_content").mount(campaign_selection)
        campaign_selection.focus()

    def action_show_people(self) -> None:
        """Show the people list screen."""
        self.query_one("#app_content").remove_children()
        person_list = PersonList()
        self.query_one("#app_content").mount(person_list)
        person_list.focus()

    def action_show_companies(self) -> None:
        """Show the company list screen."""
        self.query_one("#app_content").remove_children()
        company_list = CompanyList()
        self.query_one("#app_content").mount(company_list)
        company_list.focus()

    def action_show_prospects(self) -> None:
        """Show the prospect menu screen."""
        self.query_one("#app_content").remove_children()
        prospect_menu = ProspectMenu()
        self.query_one("#app_content").mount(prospect_menu)
        prospect_menu.focus()

    def action_select_item(self) -> None:
        """Selects the currently focused item, if the focused widget supports it."""
        focused_widget = self.focused
        if focused_widget and hasattr(focused_widget, "action_select_item"):
            focused_widget.action_select_item()
        elif isinstance(focused_widget, ListView):
            focused_widget.action_select_cursor()
        else:
            logger.warning(f"No select_item action found for focused widget: {focused_widget}")

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