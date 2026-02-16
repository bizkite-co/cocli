import logging
import os
from datetime import datetime
from typing import Any, Optional, Type, List, cast, Dict

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
from .widgets.application_view import ApplicationView, OperationsMenu
from .widgets.status_view import StatusView
from .widgets.campaign_selection import CampaignSelection
from .navigation import NavNode, ProcessRun
from ..application.services import ServiceContainer
from ..core.config import create_default_config_file

logger = logging.getLogger(__name__)

LEADER_KEY = "space"

def tui_debug_log(msg: str) -> None:
    """Direct-to-file logging for TUI events, bypasses framework config."""
    try:
        log_path = ".logs/tui_debug.log"
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} - {msg}\n")
            f.flush()
    except Exception:
        pass

class MenuBar(Horizontal):
    """A custom menu bar that highlights the active section."""
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(id="menu_bar", *args, **kwargs)
        self.active_section: str = ""

    def compose(self) -> ComposeResult:
        # Left-aligned items
        yield Label("Companies ( C)", id="menu-companies", classes="menu-item")
        yield Label("People ( P)", id="menu-people", classes="menu-item")
        
        # Spacer to push following items to the right
        yield Static("", id="menu-spacer")
        
        # Right-aligned Application item with campaign name
        app = cast("CocliApp", self.app)
        campaign_name = app.services.campaign_service.campaign_name
        yield Label(f"{campaign_name} ( A)", id="menu-application", classes="menu-item")

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
        Binding("escape", "navigate_up", "Back", show=False),
        Binding("ctrl+c", "navigate_up", "Back", show=False),
        ("alt+s", "navigate_up", "Navigate Up"),
        Binding("meta+s", "navigate_up", "Navigate Up", show=False),
        ("[", "focus_sidebar", "Focus Sidebar"),
        ("]", "focus_content", "Focus Content"),
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
        self.process_runs: List[ProcessRun] = []
        
        # Initialize Navigation Tree here to avoid circular imports at module level
        self.nav_tree: Dict[Type[Any], NavNode] = {
            # --- Companies Branch ---
            CompanyDetail: NavNode(
                widget_class=CompanyDetail,
                parent_action="action_show_companies",
                root_widget=CompanyList,
                model_type="companies"
            ),
            CompanyList: NavNode(
                widget_class=CompanyList,
                model_type="companies",
                is_branch_root=True
            ),

            # --- People Branch ---
            PersonDetail: NavNode(
                widget_class=PersonDetail,
                parent_action="action_show_people",
                root_widget=PersonList,
                model_type="people"
            ),
            PersonList: NavNode(
                widget_class=PersonList,
                model_type="people",
                is_branch_root=True
            ),

            # --- Application Branch ---
            OperationsMenu: NavNode(
                widget_class=OperationsMenu,
                parent_action="action_reset_view", 
                root_widget=ApplicationView
            ),
            StatusView: NavNode(
                widget_class=StatusView,
                parent_action="action_reset_view",
                root_widget=ApplicationView
            ),
            CampaignSelection: NavNode(
                widget_class=CampaignSelection,
                parent_action="action_reset_view",
                root_widget=ApplicationView
            ),
            ApplicationView: NavNode(
                widget_class=ApplicationView,
                is_branch_root=True
            )
        }

    def on_mount(self) -> None:
        tui_debug_log("--- APP START ---")
        self.main_content = self.query_one("#app_content", Container)
        self.menu_bar = self.query_one(MenuBar)
        create_default_config_file()
        if self.auto_show:
            self.action_show_companies()

    def action_focus_sidebar(self) -> None:
        """Focus the sidebar in views that have one (like ApplicationView)."""
        for widget in self.query("ApplicationView"):
            if widget.visible:
                cast(ApplicationView, widget).action_focus_sidebar()
                return

    def action_focus_content(self) -> None:
        """Focus the main content area."""
        for widget in self.query("ApplicationView"):
            if widget.visible:
                cast(ApplicationView, widget).action_focus_content()
                return

    async def on_key(self, event: events.Key) -> None:
        tui_debug_log(f"APP: on_key: {event.key} (focused={self.focused.__class__.__name__ if self.focused else 'None'})")
        
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
        Unifies all 'Up' navigation.
        Handles Drill-Down exit (Leaf -> Root) and List Reset (Root -> Focus List).
        """
        tui_debug_log("APP: action_navigate_up triggered")
        
        target_node = self._get_active_nav_node()
        
        if not target_node:
            tui_debug_log("APP: No active nav node detected, defaulting to companies")
            self.action_show_companies()
            return

        tui_debug_log(f"APP: Target node: {target_node.widget_class.__name__}")

        if target_node.parent_action:
            tui_debug_log(f"APP: Executing parent action: {target_node.parent_action}")
            if hasattr(self, target_node.parent_action):
                getattr(self, target_node.parent_action)()
            else:
                try:
                    w = self.query_one(target_node.widget_class)
                    if hasattr(w, target_node.parent_action):
                        getattr(w, target_node.parent_action)()
                except Exception:
                    pass
            
            # Use local capture to ensure target_node isn't None in closure
            root_widget_class = target_node.root_widget
            
            def focus_root(w_class: Type[Any] = root_widget_class) -> None:
                tui_debug_log(f"APP: Resetting view for {w_class.__name__}")
                try:
                    target = self.query_one(w_class)
                    if hasattr(target, "action_reset_view"):
                        target.action_reset_view()
                    elif hasattr(target, "action_focus_sidebar"):
                        target.action_focus_sidebar()
                except Exception as e:
                    tui_debug_log(f"APP: Failed to reset root: {e}")
            self.call_later(focus_root)
        else:
            # Already at branch root, just reset view/focus list/sidebar
            try:
                widget = self.query_one(target_node.widget_class)
                tui_debug_log(f"APP: Already at root {target_node.widget_class.__name__}, resetting view")
                if hasattr(widget, "action_reset_view"):
                    widget.action_reset_view()
                elif hasattr(widget, "action_focus_sidebar"):
                    widget.action_focus_sidebar()
            except Exception as e:
                tui_debug_log(f"APP: Failed to reset view at root: {e}")

    def _get_active_nav_node(self) -> Optional[NavNode]:
        """Finds the most specific active navigation node currently visible."""
        tui_debug_log("APP: _get_active_nav_node starting search")
        # 1. Detail Views (Leaf nodes) have priority
        for widget_class, node in self.nav_tree.items():
            if node.parent_action:
                try:
                    widgets = list(self.query(widget_class))
                    for w in widgets:
                        if w.visible:
                            tui_debug_log(f"APP: Found active leaf: {widget_class.__name__}")
                            return node
                except Exception as e:
                    tui_debug_log(f"APP: Error querying {widget_class.__name__}: {e}")
                    continue
        
        # 2. List Views (Branch nodes)
        for widget_class, node in self.nav_tree.items():
            if not node.parent_action:
                try:
                    widgets = list(self.query(widget_class))
                    for w in widgets:
                        if w.visible:
                            tui_debug_log(f"APP: Found active root: {widget_class.__name__}")
                            return node
                except Exception as e:
                    tui_debug_log(f"APP: Error querying root {widget_class.__name__}: {e}")
                    continue
        
        tui_debug_log("APP: No active nav node detected")
        return None

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
        """Escape context without search reset."""
        tui_debug_log("APP: action_escape triggered")
        node = self._get_active_nav_node()
        if node and node.parent_action:
            tui_debug_log(f"APP: Escaping from {node.widget_class.__name__} to parent")
            if hasattr(self, node.parent_action):
                getattr(self, node.parent_action)()
            else:
                try:
                    w = self.query_one(node.widget_class)
                    if hasattr(w, node.parent_action):
                        getattr(w, node.parent_action)()
                except Exception:
                    pass
        elif isinstance(self.focused, Input):
            self.focused.value = ""

if __name__ == "__main__":
    app: CocliApp = CocliApp()
    app.run()
