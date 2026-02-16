import logging
from typing import Any, Optional, Dict, Type

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Static, ListView, Input, Label, Footer
from textual.containers import Container, Horizontal
from textual import events


from .widgets.company_list import CompanyList
from .widgets.person_list import PersonList
from .widgets.master_detail import MasterDetailView
from .widgets.company_preview import CompanyPreview
from .widgets.person_detail import PersonDetail
from .widgets.company_detail import CompanyDetail
from .widgets.application_view import ApplicationView
from ..application.services import ServiceContainer
from ..core.config import create_default_config_file

logger = logging.getLogger(__name__)

LEADER_KEY = "space"

# --- Navigation Tree Documentation ---
# This map defines the "Drill-Down" relationships in the UI.
# alt+s uses this to navigate from a Branch Node (Detail) back to a Root Node (Search/List).
BRANCH_ROOTS: Dict[Type[Any], Dict[str, Any]] = {
    CompanyDetail: {
        "parent_action": "action_show_companies",
        "root_widget": CompanyList
    },
    PersonDetail: {
        "parent_action": "action_show_people",
        "root_widget": PersonList
    },
    CompanyList: {
        "parent_action": None, # Already at root of this branch
        "root_widget": CompanyList
    },
    PersonList: {
        "parent_action": None,
        "root_widget": PersonList
    }
}

class MenuBar(Horizontal):
    """A custom menu bar that highlights the active section."""
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(id="menu_bar", *args, **kwargs)
        self.active_section: str = ""

    def compose(self) -> ComposeResult:
        yield Label("Companies ( C)", id="menu-companies", classes="menu-item")
        yield Label("People ( P)", id="menu-people", classes="menu-item")
        yield Label("Application ( A)", id="menu-application", classes="menu-item")

    def set_active(self, section: str) -> None:
        for label in self.query(Label):
            label.remove_class("active-menu-item")
        
        target_id = f"menu-{section}"
        try:
            self.query_one(f"#{target_id}", Label).add_class("active-menu-item")
        except Exception:
            pass

class CocliApp(App[None]):
    """A Textual app to manage cocli."""

    dark: bool = False
    CSS_PATH = "tui.css"
    
    BINDINGS = [
        ("l", "select_item", "Select"),
        ("q", "quit", "Quit"),
        Binding("ctrl+c", "escape", "Escape", show=False),
        ("alt+s", "navigate_up", "Navigate Up"),
    ]

    leader_mode: bool = False
    leader_key_buffer: str = ""

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield MenuBar()
        yield Container(id="app_content")
        yield Footer()

    def __init__(self, services: Optional[ServiceContainer] = None, auto_show: bool = True, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.services = services or ServiceContainer()
        self.auto_show = auto_show

    def on_mount(self) -> None:
        self.main_content = self.query_one("#app_content", Container)
        self.menu_bar = self.query_one(MenuBar)
        create_default_config_file()
        if self.auto_show:
            self.action_show_companies()

    async def on_key(self, event: events.Key) -> None:
        if event.key == LEADER_KEY:
            self.leader_mode = True
            self.leader_key_buffer = LEADER_KEY
            event.prevent_default()
            return

        if self.leader_mode:
            self.leader_key_buffer += event.key
            
            if self.leader_key_buffer == LEADER_KEY + "c":
                self.call_later(self.action_show_companies)
            elif self.leader_key_buffer == LEADER_KEY + "p":
                self.call_later(self.action_show_people)
            elif self.leader_key_buffer == LEADER_KEY + "a":
                self.call_later(self.action_show_application)
            
            self.reset_leader_mode()
            event.prevent_default()
            return

    def reset_leader_mode(self) -> None:
        self.leader_mode = False
        self.leader_key_buffer = ""

    def action_navigate_up(self) -> None:
        """
        Navigates 'Up' from a leaf node (Detail) to its branch root (Search/List).
        If already at a branch root, focuses the search box.
        """
        # Iterate through the registry to find the active context
        for widget_class, config in BRANCH_ROOTS.items():
            # We check if the widget exists AND is currently visible in the DOM
            try:
                widget = self.query_one(widget_class)
                if not widget.visible:
                    continue
            except Exception:
                continue

            # 1. If we are in a detail/branch node, navigate up to the root node
            parent_action = config.get("parent_action")
            if parent_action:
                getattr(self, parent_action)()
            
            # 2. Focus/Reset search on the root widget of this specific branch
            def reset_search(w_class: Type[Any] = config["root_widget"]) -> None:
                try:
                    target = self.query_one(w_class)
                    if hasattr(target, "action_search_fresh"):
                        target.action_search_fresh()
                except Exception:
                    pass
            
            self.call_later(reset_search)
            return

    def on_person_list_person_selected(self, message: PersonList.PersonSelected) -> None:
        self.query_one("#app_content").remove_children()
        self.query_one("#app_content").mount(PersonDetail(person_slug=message.person_slug))

    def on_company_list_company_selected(self, message: CompanyList.CompanySelected) -> None:
        company_slug = message.company_slug
        try:
            company_data = self.services.get_company_details(company_slug)
            if company_data:
                self.query_one("#app_content").remove_children()
                company_detail = CompanyDetail(company_data)
                self.query_one("#app_content").mount(company_detail)
                company_detail.styles.display = "block"
            else:
                self.bell()
        except Exception:
            self.bell()

    def action_show_companies(self) -> None:
        """Show the company list view."""
        self.menu_bar.set_active("companies")
        self.main_content.remove_children()
        company_list = CompanyList()
        company_preview = CompanyPreview(Static("Select a company to see details."), id="company-preview")
        self.main_content.mount(MasterDetailView(master=company_list, detail=company_preview))

    def action_show_people(self) -> None:
        """Show the person list view."""
        self.menu_bar.set_active("people")
        self.main_content.remove_children()
        self.main_content.mount(PersonList())

    def action_show_application(self) -> None:
        """Show the application view."""
        self.menu_bar.set_active("application")
        self.main_content.remove_children()
        self.main_content.mount(ApplicationView())

    def on_application_view_campaign_activated(self, message: ApplicationView.CampaignActivated) -> None:
        self.notify(f"Campaign Activated: {message.campaign_name}")
        self.action_show_companies()

    def action_select_item(self) -> None:
        focused_widget = self.focused
        if not focused_widget:
            return
        if hasattr(focused_widget, "action_select_item"):
            focused_widget.action_select_item()
        elif isinstance(focused_widget, ListView):
            focused_widget.action_select_cursor()

    def action_escape(self) -> None:
        """Escape the current context (return to previous level without search reset)."""
        for widget_class, config in BRANCH_ROOTS.items():
            try:
                widget = self.query_one(widget_class)
                if not widget.visible:
                    continue
            except Exception:
                continue

            parent_action = config.get("parent_action")
            if parent_action:
                getattr(self, parent_action)()
                return
        
        if isinstance(self.focused, Input):
            self.focused.value = ""

if __name__ == "__main__":
    app: CocliApp = CocliApp()
    app.run()
