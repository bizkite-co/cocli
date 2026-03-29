import logging
import os
import asyncio
import time
from datetime import datetime
from contextlib import contextmanager
from typing import (
    Any,
    Optional,
    Type,
    List,
    cast,
    Dict,
    Generator,
    AsyncGenerator,
    Callable,
)

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Static, ListView, Input, Label, Footer
from textual.containers import Container, Horizontal
from textual import events, on
from textual.command import Provider, Hit
from textual.screen import ModalScreen

from .widgets.company_list import CompanyList
from .widgets.person_list import PersonList
from .widgets.company_preview import CompanyPreview
from .widgets.person_detail import PersonDetail
from .widgets.company_detail import CompanyDetail
from .widgets.application_view import ApplicationView
from .widgets.status_view import StatusView
from .widgets.campaign_selection import CampaignSelection
from .widgets.company_search import CompanySearchView
from .widgets.template_list import TemplateList
from .widgets.event_curation import EventCurationView
from .navigation import NavNode, ProcessRun
from .navigation_manager import NavigationStateManager
from ..utils.browser_manager import BrowserManager
from ..application.services import ServiceContainer
from ..core.config import create_default_config_file, is_campaign_overridden

logger = logging.getLogger(__name__)

LEADER_KEY = "space"


def tui_debug_log(msg: str) -> None:
    """Direct-to-file logging for TUI events, bypasses framework config."""
    if os.environ.get("TUI_DEBUG", "").lower() not in ("1", "true", "yes"):
        return
    try:
        log_path = ".logs/tui_debug.log"
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} - {msg}\n")
            f.flush()
    except Exception:
        pass


@contextmanager
def time_perf(label: str) -> Generator[None, None, None]:
    start = time.perf_counter()
    yield
    end = time.perf_counter()
    tui_debug_log(f"PERF: {label} took {end - start:.4f}s")


class MenuBar(Horizontal):
    """A custom menu bar that highlights the active section."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.active_section: str = ""

    def compose(self) -> ComposeResult:
        from ..core.environment import get_environment, Environment

        env = get_environment()

        # Left-aligned items
        yield Label("Companies ( C)", id="menu-companies", classes="menu-item")
        yield Label("People ( P)", id="menu-people", classes="menu-item")
        yield Label("Events ( E)", id="menu-events", classes="menu-item")
        yield Label("Admin ( A)", id="menu-admin", classes="menu-item")

        # Environment Indicator (Visible only if not PROD)
        if env != Environment.PROD:
            color = "bold yellow"
            yield Label(
                f"[{color}] {env.value.upper()} [/]",
                id="menu-environment",
                classes="menu-item",
            )

        # Spacer to push following items to the right
        yield Static("", id="menu-spacer")

        # Activity Indicator
        yield Label("", id="menu-activity", classes="menu-item")

        # Right-aligned Application item with placeholder (updated on mount)
        yield Label("Application ( A)", id="menu-application", classes="menu-item")

    def on_mount(self) -> None:
        """Update the campaign name label on mount to avoid blocking compose."""
        self.refresh_campaign()

    def set_activity(self, msg: str) -> None:
        try:
            label = self.query_one("#menu-activity", Label)
            if msg:
                label.update(f"[bold yellow] {msg}...[/bold yellow]")
            else:
                label.update("")
        except Exception:
            pass

    def set_active(self, section: str) -> None:
        for label in self.query(Label):
            label.remove_class("active-menu-item")

        target_id = f"menu-{section}"
        try:
            self.query_one(f"#{target_id}", Label).add_class("active-menu-item")
        except Exception:
            pass

    def refresh_campaign(self) -> None:
        """Updates the campaign name label in the menu bar."""
        app = cast("CocliApp", self.app)
        campaign_name = app.services.campaign_name or "[No Campaign]"

        # Add visual indicator if the campaign is overridden (from CLI or Environment)
        if is_campaign_overridden():
            display_text = f"[bold white on blue] {campaign_name} [/] ( A)"
        else:
            display_text = f"{campaign_name} ( A)"

        try:
            self.query_one("#menu-application", Label).update(display_text)
        except Exception:
            pass


class CreateTaskModal(ModalScreen[bool]):
    """A modal screen for creating a new task."""

    def compose(self) -> ComposeResult:
        yield Container(
            Label("Create New Task", id="modal-title"),
            Input(placeholder="Task Title", id="task-title"),
            Input(placeholder="Slug (optional)", id="task-slug"),
            Input(placeholder="Description (optional)", id="task-body"),
            Horizontal(
                Static("Create as DRAFT?"),
                Static("  "),
                Label("NO", id="draft-toggle"),
                id="draft-row",
            ),
            Horizontal(Static("Enter to Create, ESC to Cancel"), id="modal-footer"),
            id="create-task-modal",
        )

    def on_mount(self) -> None:
        self.is_draft = False
        self.query_one("#task-title").focus()

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            self.dismiss(False)
        elif event.key == "enter":
            self._create_task()
        elif event.key == "d" and not isinstance(self.focused, Input):
            self._toggle_draft()

    def _toggle_draft(self) -> None:
        self.is_draft = not self.is_draft
        label = self.query_one("#draft-toggle", Label)
        label.update("YES" if self.is_draft else "NO")
        label.styles.color = "yellow" if self.is_draft else "white"

    def _create_task(self) -> None:
        title = self.query_one("#task-title", Input).value
        if not title:
            self.app.notify("Task title is required", severity="error")
            return

        slug = self.query_one("#task-slug", Input).value
        body = self.query_one("#task-body", Input).value

        try:
            # We call the command logic directly.
            # Note: create_task uses typer.Exit so we might need to handle it
            # but for TUI we can just call the manager directly if needed.
            from ..core.tasks import TaskIndexManager
            from ..models.tasks import MissionTask, TaskStatus
            from ..utils.textual_utils import sanitize_id

            if not slug:
                slug = sanitize_id(title)

            manager = TaskIndexManager()
            if any(t.slug == slug for t in manager.tasks) or manager._is_task_completed(
                slug
            ):
                self.app.notify(f"Task '{slug}' already exists", severity="error")
                return

            status = TaskStatus.DRAFT if self.is_draft else TaskStatus.PENDING
            folder = "draft" if self.is_draft else "pending"

            # Use issues_root from manager to ensure consistency
            task_file = manager.issues_root / folder / f"{slug}.md"
            task_file.parent.mkdir(parents=True, exist_ok=True)
            task_file.write_text(f"# {title}\n\n{body or ''}", encoding="utf-8")

            new_task = MissionTask(slug=slug)
            new_task.title = title
            new_task.status = status
            manager.tasks.append(new_task)

            manager.save()

            self.app.notify(f"Task created: {slug}")
            self.dismiss(True)
        except Exception as e:
            self.app.notify(f"Error creating task: {e}", severity="error")


class CocliCommandProvider(Provider):
    """Provides Cocli-specific commands to the Textual Command Palette."""

    def get_commands(self) -> Dict[str, tuple[Callable[[], Any], str]]:
        """Returns a registry of all available commands."""
        app = cast("CocliApp", self.app)
        return {
            "Show Companies": (
                app.action_show_companies,
                "Switch to the companies search and list view.",
            ),
            "Show People": (app.action_show_people, "Switch to the people list view."),
            "Show Events": (
                app.action_show_events,
                "Switch to the community event curation view.",
            ),
            "Show Application": (
                app.action_show_application,
                "Switch to the application status and campaign view.",
            ),
            "Focus Sidebar": (
                app.action_focus_sidebar,
                "Focus the sidebar/template pane in the current view.",
            ),
            "Focus Content": (
                app.action_focus_content,
                "Focus the main content/list pane in the current view.",
            ),
            "Create Task": (
                self.action_create_task,
                "Create a new task in the mission queue.",
            ),
        }

    async def search(self, query: str) -> AsyncGenerator[Hit, None]:
        """Search for commands matching the query."""
        matcher = self.matcher(query)
        app = cast("CocliApp", self.app)

        from ..core.environment import get_environment, Environment

        env = get_environment()

        commands = [
            (
                "Show Companies",
                app.action_show_companies,
                "Switch to the companies search and list view.",
            ),
            ("Show People", app.action_show_people, "Switch to the people list view."),
            (
                "Show Events",
                app.action_show_events,
                "Switch to the community event curation view.",
            ),
            (
                "Show Admin",
                app.action_show_admin,
                "Switch to the system admin and campaign view.",
            ),
            (
                "Focus Sidebar",
                app.action_focus_sidebar,
                "Focus the sidebar/template pane in the current view.",
            ),
            (
                "Focus Content",
                app.action_focus_content,
                "Focus the main content/list pane in the current view.",
            ),
            (
                "Create Task",
                self.action_create_task,
                "Create a new task in the mission queue.",
            ),
            ("Quit", app.action_quit, "Exit the application."),
        ]

        if env != Environment.PROD:
            commands.append(
                (
                    "Refresh DEV from PROD",
                    app.action_refresh_dev,
                    "Clones PROD data into the current DEV environment.",
                )
            )

        # Sort by MRU (Most Recent First)
        def get_mru_score(cmd_name: str) -> int:
            if cmd_name in app.command_mru:
                return 100 - app.command_mru.index(cmd_name)
            return 0

        # Primary sort by MRU, secondary sort by Name (alphabetical)
        sorted_commands = sorted(
            commands, key=lambda x: (get_mru_score(x[0]), x[0]), reverse=True
        )

        if not query:
            # Show top 5 MRU or defaults
            for name, action, help_text in sorted_commands[:5]:
                yield Hit(1.0, name, self.action_wrapper(name, action), help=help_text)
        else:
            for name, action, help_text in sorted_commands:
                score = matcher.match(name)
                if score > 0:
                    yield Hit(
                        score,
                        matcher.highlight(name),
                        self.action_wrapper(name, action),
                        help=help_text,
                    )

    def action_wrapper(self, name: str, action: Callable[[], Any]) -> Callable[[], Any]:
        """Wraps an action to update MRU on execution."""

        async def wrapped() -> None:
            cast("CocliApp", self.app).update_command_mru(name)
            res = action()
            if asyncio.iscoroutine(res):
                await res

        return wrapped

    def wrap_action(self, name: str, action: Callable[[], Any]) -> Callable[[], Any]:
        """Wraps an action to record its use in history before execution."""
        app = cast("CocliApp", self.app)

        def wrapper() -> Any:
            app.record_command(name)
            if asyncio.iscoroutinefunction(action):
                return app.run_worker(action())
            return action()

        return wrapper

    def action_create_task(self) -> None:
        """Action to show the create task modal."""
        self.app.push_screen(CreateTaskModal())


class CocliApp(App[None]):
    """A Textual app to manage cocli."""

    dark: bool = False
    CSS_PATH = "tui.css"

    # Command palette providers
    COMMANDS = {CocliCommandProvider}

    BINDINGS = [
        ("l", "select_item", "Select"),
        ("h", "navigate_up", "Back"),
        ("q", "quit", "Quit"),
        Binding("escape", "navigate_up", "Back", show=False),
        Binding("ctrl+c", "navigate_up", "Back", show=False),
        ("alt+s", "navigate_up", "Navigate Up"),
        Binding("meta+s", "navigate_up", "Navigate Up", show=False),
        ("[", "focus_sidebar", "Focus Sidebar"),
        ("]", "focus_content", "Focus Content"),
        ("t", "focus_templates", "Templates"),
        Binding("ctrl+p", "command_palette", "Commands", show=True),
    ]

    leader_mode: bool = False
    leader_key_buffer: str = ""

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield MenuBar(id="menu_bar")
        yield Container(id="app_content")
        yield Footer()

    def __init__(
        self,
        services: Optional[ServiceContainer] = None,
        auto_show: bool = True,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.services = services or ServiceContainer()
        self.auto_show = auto_show
        self.process_runs: List[ProcessRun] = []
        self.command_mru: List[str] = []
        self.nav_manager = NavigationStateManager(self)
        self.browser_manager = BrowserManager()

        # Command Palette History (Last used commands at the top)
        self.command_history: List[str] = [
            "Show Companies",
            "Show People",
            "Show Events",
            "Show Application",
            "Create Task",
        ]

        # Explicitly ensure the OperationService uses our shared services container
        # to prevent it from spawning its own ServiceContainer (which breaks mocks)
        if hasattr(self.services, "operation_service"):
            # Trigger lazy load if it's a property, but ensure it's synced
            _ = self.services.operation_service
        self.nav_tree: Dict[Type[Any], NavNode] = {
            # --- Companies Branch ---
            CompanyDetail: NavNode(
                widget_class=CompanyDetail,
                parent_action="action_show_companies",
                root_widget=CompanyList,
                model_type="companies",
            ),
            CompanyList: NavNode(
                widget_class=CompanyList,
                parent_action="action_focus_templates",
                root_widget=CompanySearchView,
                model_type="companies",
            ),
            CompanySearchView: NavNode(
                widget_class=CompanySearchView,
                model_type="companies",
                is_branch_root=True,
            ),
            # --- People Branch ---
            PersonDetail: NavNode(
                widget_class=PersonDetail,
                parent_action="action_show_people",
                root_widget=PersonList,
                model_type="people",
            ),
            PersonList: NavNode(
                widget_class=PersonList, model_type="people", is_branch_root=True
            ),
            # --- Admin Branch ---
            StatusView: NavNode(
                widget_class=StatusView,
                parent_action="action_show_admin",
                root_widget=ApplicationView,
            ),
            CampaignSelection: NavNode(
                widget_class=CampaignSelection,
                parent_action="action_show_admin",
                root_widget=ApplicationView,
            ),
            ApplicationView: NavNode(widget_class=ApplicationView, is_branch_root=True),
            # --- Events Branch ---
            EventCurationView: NavNode(
                widget_class=EventCurationView, is_branch_root=True
            ),
        }

    def record_command(self, name: str) -> None:
        """Records a command use in history, moving it to the top."""
        if name in self.command_history:
            self.command_history.remove(name)
        self.command_history.insert(0, name)
        # Limit history size
        if len(self.command_history) > 15:
            self.command_history = self.command_history[:15]

    def _start_pi_sync_background(self) -> None:
        """
        Check if PI sync is needed and run it in a background thread.
        This is non-blocking and updates the timestamp on completion.
        """
        import os

        # Skip auto-sync if environment variable is set
        if os.environ.get("COCLI_SKIP_AUTO_SYNC", "").lower() in ("1", "true", "yes"):
            tui_debug_log("APP: Skipping PI sync (COCLI_SKIP_AUTO_SYNC=1)")
            return

        from ..core.config import get_campaign
        from cocli.core.sync_tracker import SyncTracker
        import threading
        import logging

        logger = logging.getLogger(__name__)
        campaign = get_campaign()

        if not campaign:
            return

        tracker = SyncTracker(campaign)
        if not tracker.needs_sync():
            tui_debug_log(f"APP: PI sync not needed for {campaign}")
            return

        def _run_sync() -> None:
            try:
                from cocli.application.pi_sync_service import PiSyncService

                service = PiSyncService(campaign)
                service.sync_all_nodes(blocking=True)
                summary = service.get_summary()

                if summary["failed"] == 0:
                    tracker.update_last_sync()
                    logger.info(
                        f"PI sync completed: {summary['total_files_synced']} files synced"
                    )
                else:
                    logger.warning(
                        f"PI sync completed with {summary['failed']} failures"
                    )
            except Exception as e:
                logger.error(f"PI sync failed: {e}")

        thread = threading.Thread(target=_run_sync, daemon=True)
        thread.start()
        tui_debug_log(f"APP: Started background PI sync for campaign: {campaign}")

    async def on_mount(self) -> None:
        with time_perf("APP: on_mount"):
            tui_debug_log("--- APP START ---")
            self.main_content = self.query_one("#app_content", Container)
            self.menu_bar = self.query_one(MenuBar)

            with time_perf("APP: create_default_config_file"):
                create_default_config_file()

            # Start the Gossip Bridge in background (non-blocking)
            import threading
            from ..core.gossip_bridge import bridge

            def start_bridge() -> None:
                try:
                    if bridge:
                        bridge.start()
                        tui_debug_log("APP: Gossip Bridge started.")
                except Exception as e:
                    tui_debug_log(f"APP: Gossip Bridge failed to start: {e}")

            bridge_thread = threading.Thread(target=start_bridge, daemon=True)
            bridge_thread.start()

            # Start PI sync check in background (non-blocking)
            self._start_pi_sync_background()

            if self.auto_show:
                await self.action_show_companies()

    async def on_unmount(self) -> None:
        """Handle cleanup on application exit."""
        from ..core.gossip_bridge import bridge

        if bridge:
            try:
                self.notify("Stopping Gossip Bridge...", timeout=2)
                with time_perf("APP: bridge.stop()"):
                    bridge.stop()
                tui_debug_log("APP: Gossip Bridge stopped.")
            except Exception as e:
                tui_debug_log(f"APP: Gossip Bridge failed to stop: {e}")

    def action_focus_sidebar(self) -> None:
        """Focus the sidebar in views that have one (like ApplicationView)."""
        for widget in self.query(ApplicationView):
            if widget.visible:
                widget.action_focus_sidebar()
                return

    def action_focus_content(self) -> None:
        """Focus the main content area."""
        for widget in self.query(ApplicationView):
            if widget.visible:
                widget.action_focus_content()
                return

    # Keys allowed to bubble and trigger shortcuts even when typing
    INPUT_CONTROL_KEYS = {
        "tab",
        "backtab",
        "enter",
        "escape",
        "ctrl+c",
        "alt+s",
        "meta+s",
        "f1",
        "f2",
        "f3",
        "f4",
        "f5",
        "f6",
        "f7",
        "f8",
        "f9",
        "f10",
        "f11",
        "f12",
    }

    async def on_key(self, event: events.Key) -> None:
        # 0. CRITICAL Protection: If an Input is focused, do NOT intercept shortcuts
        # or Leader mode unless they are explicit control keys.
        if isinstance(self.focused, Input):
            if event.key not in self.INPUT_CONTROL_KEYS:
                # This is a typing character (including 'space').
                # Let it bubble to the Input widget by NOT calling event.stop()
                # but we must also NOT handle it as a shortcut.
                return

        # 1. HIGH PRIORITY: Leader mode must intercept keys before anyone else
        if event.key == LEADER_KEY:
            self.leader_mode = True
            self.leader_key_buffer = LEADER_KEY
            tui_debug_log(f"APP: Leader mode active (key={event.key})")
            event.stop()
            event.prevent_default()
            return

        if self.leader_mode:
            self.leader_key_buffer += event.key
            tui_debug_log(f"APP: Leader buffer: {self.leader_key_buffer}")

            if self.leader_key_buffer == LEADER_KEY + "c":
                await self.action_show_companies()
            elif self.leader_key_buffer == LEADER_KEY + "p":
                await self.action_show_people()
            elif self.leader_key_buffer == LEADER_KEY + "e":
                await self.action_show_events()
            elif self.leader_key_buffer == LEADER_KEY + "a":
                await self.action_show_admin()

            self.reset_leader_mode()
            event.stop()
            event.prevent_default()
            return

        tui_debug_log(
            f"APP: on_key: {event.key} (focused={self.focused.__class__.__name__ if self.focused else 'None'})"
        )

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
            self.run_worker(self.action_show_companies())
            return

        tui_debug_log(f"APP: Target node: {target_node.widget_class.__name__}")

        if target_node.parent_action:
            tui_debug_log(f"APP: Scheduling parent action: {target_node.parent_action}")

            p_action = target_node.parent_action
            r_widget_class = target_node.root_widget
            w_class = target_node.widget_class

            def do_nav_up() -> None:
                if hasattr(self, p_action):
                    attr = getattr(self, p_action)
                    if asyncio.iscoroutinefunction(attr):
                        self.run_worker(attr())
                    else:
                        attr()
                else:
                    try:
                        w = self.query_one(w_class)
                        if hasattr(w, p_action):
                            getattr(w, p_action)()
                    except Exception:
                        pass

                # Use local capture to ensure target_node isn't None in closure
                if r_widget_class:
                    # Skip auto-reset if returning from a detail view to preserve search state
                    is_detail = any(
                        leaf in w_class.__name__.lower() for leaf in ["detail", "modal"]
                    )
                    if not is_detail:
                        tui_debug_log(
                            f"APP: Resetting view for {r_widget_class.__name__}"
                        )
                        try:
                            target = self.query_one(r_widget_class)
                            if hasattr(target, "action_reset_view"):
                                target.action_reset_view()
                            elif hasattr(target, "action_focus_sidebar"):
                                target.action_focus_sidebar()
                            elif hasattr(
                                target, "action_focus_template"
                            ):  # For SearchView
                                target.action_focus_template()
                        except Exception as e:
                            tui_debug_log(f"APP: Failed to reset root: {e}")

            self.call_later(do_nav_up)
        else:
            # Already at branch root, just reset view/focus list/sidebar
            try:
                widget = self.query_one(target_node.widget_class)
                tui_debug_log(
                    f"APP: Already at root {target_node.widget_class.__name__}, resetting view"
                )

                # SPECIAL CASE: CompanySearchView. Navigate Up should focus Templates if we are in Search
                if isinstance(widget, CompanySearchView):
                    tui_debug_log("APP: Focus Templates in CompanySearchView")
                    widget.action_reset_view()
                elif hasattr(widget, "action_reset_view"):
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
                        if w.visible and w.has_focus_within:
                            tui_debug_log(
                                f"APP: Found active leaf: {widget_class.__name__}"
                            )
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
                        if w.visible and w.has_focus_within:
                            tui_debug_log(
                                f"APP: Found active root: {widget_class.__name__}"
                            )
                            return node
                except Exception as e:
                    tui_debug_log(
                        f"APP: Error querying root {widget_class.__name__}: {e}"
                    )
                    continue

        tui_debug_log("APP: No active nav node detected")
        return None

    def on_person_list_person_selected(
        self, message: PersonList.PersonSelected
    ) -> None:
        content = self.query_one("#app_content")
        # Hide Branch Roots, Remove Details
        for child in content.children:
            if isinstance(child, (CompanySearchView, PersonList, ApplicationView)):
                child.display = False
            else:
                child.remove()

        content.mount(PersonDetail(person_slug=message.person_slug))

    def on_company_list_company_selected(
        self, message: CompanyList.CompanySelected
    ) -> None:
        company_slug = message.company_slug
        try:
            company_data = self.services.get_company_details(company_slug)
            if company_data:
                content = self.query_one("#app_content")
                # Hide Branch Roots, Remove Details
                for child in content.children:
                    if isinstance(
                        child, (CompanySearchView, PersonList, ApplicationView)
                    ):
                        child.display = False
                    else:
                        child.remove()

                company_detail = CompanyDetail(company_data)
                content.mount(company_detail)
                company_detail.styles.display = "block"
            else:
                self.bell()
        except Exception:
            self.bell()

    def update_command_mru(self, name: str) -> None:
        """Updates the most recently used command list."""
        if name in self.command_mru:
            self.command_mru.remove(name)
        self.command_mru.insert(0, name)
        self.command_mru = self.command_mru[:5]

    async def action_show_companies(self) -> None:
        """Show the company list view."""
        with time_perf("APP: action_show_companies"):
            try:
                menu_bar = self.query_one(MenuBar)
                menu_bar.set_activity("Switching")
                menu_bar.set_active("companies")
            except Exception:
                pass

            content = self.main_content
            search_view = None

            # 1. Find or Hide children
            for child in content.children:
                if isinstance(child, CompanySearchView):
                    search_view = child
                    child.display = True
                elif isinstance(child, (PersonList, ApplicationView)):
                    child.display = False
                else:
                    child.remove()  # Remove detail views

            if search_view:
                # Restore focus to company list instead of template list to preserve flow
                search_view.company_list.query_one(ListView).focus()
                self.menu_bar.set_activity("")
                return

            # 2. Create fresh if not found (initial startup)
            template_list = TemplateList(
                id="search-templates-pane", classes="search-pane"
            )
            company_list = CompanyList(
                id="search-companies-pane", classes="search-pane"
            )
            company_preview = CompanyPreview(
                Static("Select a company to see details."),
                id="search-preview-pane",
                classes="search-pane",
            )

            search_view = CompanySearchView(
                template_list=template_list,
                company_list=company_list,
                company_preview=company_preview,
            )

            with time_perf("APP: mount(CompanySearchView)"):
                await self.main_content.mount(search_view)

            # Start the search
            if self.services.sync_search:
                await company_list.perform_search("")
            else:
                self.run_worker(company_list.perform_search(""))

            # Focus the template list after initial paint
            def focus_templates() -> None:
                try:
                    if search_view.is_mounted:
                        template_list.focus_list()
                except Exception:
                    pass
                self.menu_bar.set_activity("")

            self.call_after_refresh(focus_templates)

    def action_focus_templates(self) -> None:
        """Focus the template list in search view."""
        for search_view in self.query(CompanySearchView):
            if search_view.visible:
                search_view.action_focus_template()
                return

    async def action_show_people(self) -> None:
        """Show the person list view."""
        with time_perf("APP: action_show_people"):
            try:
                menu_bar = self.query_one(MenuBar)
                menu_bar.set_activity("Switching")
                menu_bar.set_active("people")
            except Exception:
                pass

            content = self.main_content
            person_list = None

            for child in content.children:
                if isinstance(child, PersonList):
                    person_list = child
                    child.display = True
                elif isinstance(child, (CompanySearchView, ApplicationView)):
                    child.display = False
                else:
                    child.remove()

            if person_list:
                person_list.focus()
                self.menu_bar.set_activity("")
                return

            await self.main_content.mount(PersonList())
            self.menu_bar.set_activity("")

    async def action_show_events(self) -> None:
        """Show the community event curation view."""
        with time_perf("APP: action_show_events"):
            self.menu_bar.set_activity("Switching")
            self.menu_bar.set_active("events")

            content = self.main_content
            event_view = None

            for child in content.children:
                if isinstance(child, EventCurationView):
                    event_view = child
                    child.display = True
                elif isinstance(
                    child, (CompanySearchView, PersonList, ApplicationView)
                ):
                    child.display = False
                else:
                    child.remove()

            if event_view:
                event_view.action_focus_master()
                self.menu_bar.set_activity("")
                return

            event_view = EventCurationView()
            await self.main_content.mount(event_view)
            self.menu_bar.set_activity("")

    async def action_show_admin(self) -> None:
        """Show the system admin and campaign view."""
        with time_perf("APP: action_show_admin"):
            tui_debug_log("APP: action_show_admin starting")
            try:
                menu_bar = self.query_one(MenuBar)
                menu_bar.set_activity("Loading")
                menu_bar.set_active("admin")
            except Exception:
                pass

            content = self.main_content
            app_view = None

            for child in content.children:
                if isinstance(child, ApplicationView):
                    app_view = child
                    child.display = True
                elif isinstance(child, (CompanySearchView, PersonList)):
                    child.display = False
                else:
                    child.remove()

            if app_view:
                app_view.action_focus_sidebar()
                self.menu_bar.set_activity("")
                return

            app_view = ApplicationView()
            await self.main_content.mount(app_view)
            tui_debug_log("APP: action_show_admin finished")

            # Aggressive focus
            def do_focus() -> None:
                try:
                    app_view.action_focus_sidebar()
                except Exception as e:
                    tui_debug_log(f"APP: Failed to focus ApplicationView: {e}")
                self.menu_bar.set_activity("")

            self.call_after_refresh(do_focus)

    # Alias for backward compatibility
    async def action_show_application(self) -> None:
        await self.action_show_admin()

    async def action_refresh_dev(self) -> None:
        """Triggers a local DEV data refresh from PROD."""
        from ..core.environment import get_environment, Environment

        if get_environment() == Environment.PROD:
            self.notify("Cannot refresh-dev while in PROD mode.", severity="error")
            return

        self.notify("Refreshing DEV data from PROD... (rsync)")

        async def run_refresh() -> None:
            result = await self.services.operation_service.execute("op_refresh_dev")
            if result.get("status") == "success":
                self.notify("DEV environment refreshed successfully!")
            else:
                self.notify(
                    f"Refresh failed: {result.get('message')}", severity="error"
                )

        self.run_worker(run_refresh())

    @on(ApplicationView.CampaignActivated)
    async def on_application_view_campaign_activated(
        self, message: ApplicationView.CampaignActivated
    ) -> None:
        with time_perf("APP: on_application_view_campaign_activated"):
            self.notify(f"Campaign Activated: {message.campaign_name}")
            # Refresh the service container's campaign-dependent services
            self.services.set_campaign(message.campaign_name)
            self.query_one(MenuBar).refresh_campaign()
            await self.action_show_companies()

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
            self.action_navigate_up()
        elif isinstance(self.focused, Input):
            self.focused.value = ""


if __name__ == "__main__":
    app: CocliApp = CocliApp()
    app.run()
