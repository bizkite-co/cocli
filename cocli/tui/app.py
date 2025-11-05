import logging
import toml

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Static, ListView, Input
from textual.containers import Container
from textual import events # Import events for on_key


from .widgets.campaign_selection import CampaignSelection
from .widgets.company_list import CompanyList
from .widgets.person_list import PersonList
from .widgets.person_detail import PersonDetail
from .widgets.prospect_menu import ProspectMenu
from .widgets.company_detail import CompanyDetail
from .widgets.campaign_detail import CampaignDetail
from ..application.company_service import get_company_details_for_view
from ..models.campaign import Campaign
from ..core.config import get_campaign_dir, create_default_config_file
from ..core import logging_config

logger = logging.getLogger(__name__)

LEADER_KEY = "space"

class CocliApp(App[None]):
    """A Textual app to manage cocli."""

    dark: bool = False
    CSS_PATH = "tui.css"
    
    BINDINGS = [
        # General
        ("l", "select_item", "Select"),
        ("q", "quit", "Quit"),
        Binding("ctrl+c", "escape", "Escape", show=False),
    ]

    leader_mode: bool = False
    leader_key_buffer: str = ""

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        yield Static(f"[b]Campaigns[/b] ({LEADER_KEY.upper()}+A) | [b]People[/b] ({LEADER_KEY.upper()}+P) | [b]Companies[/b] ({LEADER_KEY.upper()}+C) | [b]Prospect[/b] ({LEADER_KEY.upper()}+S)", id="menu_bar")
        yield Container(id="app_content")

    def on_mount(self) -> None:
        create_default_config_file()
        logging_config.setup_file_logging("tui", file_level=logging.DEBUG) # Moved logging setup here

    async def on_key(self, event: events.Key) -> None:
        logger.debug(f"Key pressed: {event.key}")
        if event.key == LEADER_KEY:
            self.leader_mode = True
            self.leader_key_buffer = LEADER_KEY
            event.prevent_default() # Prevent the space key from being processed further
            return

        if self.leader_mode:
            self.leader_key_buffer += event.key
            logger.debug(f"Leader key buffer: {self.leader_key_buffer}")
            
            # Check for leader key combinations
            if self.leader_key_buffer == LEADER_KEY + "c":
                self.call_later(self.action_show_companies)
            elif self.leader_key_buffer == LEADER_KEY + "p":
                self.call_later(self.action_show_people)
            elif self.leader_key_buffer == LEADER_KEY + "s":
                self.call_later(self.action_show_prospects)
            elif self.leader_key_buffer == LEADER_KEY + "a":
                self.call_later(self.action_show_campaigns)
            else:
                logger.warning(f"Unknown leader key combination: {self.leader_key_buffer}")
            
            self.reset_leader_mode()
            event.prevent_default() # Prevent the key from being processed further
            return
        
        # If not in leader mode, let Textual handle other bindings
        # The default Textual binding handler will be called after this method
        # if event.prevent_default() is not called.

    def reset_leader_mode(self) -> None:
        self.leader_mode = False
        self.leader_key_buffer = ""








    def on_person_list_person_selected(self, message: PersonList.PersonSelected) -> None:
        """Handle PersonSelected message from PersonList."""
        logger.debug(f"on_person_list_person_selected called with slug: {message.person_slug}")
        self.query_one("#app_content").remove_children()
        self.query_one("#app_content").mount(PersonDetail(person_slug=message.person_slug))

    def on_company_list_company_selected(self, message: CompanyList.CompanySelected) -> None:
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

        self.push_screen(CampaignDetail(campaign=campaign))

    async def action_show_campaigns(self) -> None:
        """Show the campaigns selection screen."""
        logger.debug("action_show_campaigns invoked")
        self.push_screen(CampaignSelection())

    async def action_show_people(self) -> None:
        """Show the people list screen."""
        logger.debug("action_show_people invoked")
        self.push_screen(PersonList())

    async def action_show_companies(self) -> None:
        """Show the company list screen."""
        logger.debug("action_show_companies called")
        self.query_one("#app_content").remove_children()
        company_list = CompanyList()
        self.query_one("#app_content").mount(company_list)
        company_list.focus()

    async def action_show_prospects(self) -> None:
        """Show the prospect menu screen."""
        logger.debug("action_show_prospects invoked")
        self.push_screen(ProspectMenu())

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

    def action_escape(self) -> None:
        """Escape the current context (pop screen or clear input)."""
        if len(self.screen_stack) > 1:
            self.pop_screen()
        else:
            focused_widget = self.focused
            if isinstance(focused_widget, Input):
                focused_widget.value = ""
                logger.debug("Cleared focused input field.")
            else:
                logger.debug("Escape pressed, but no screen to pop and no input to clear.")

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