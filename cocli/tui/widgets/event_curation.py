import logging
from typing import Optional, cast, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..app import CocliApp

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import ListView, ListItem, Label, Static
from textual import on
from textual.binding import Binding
from textual.message import Message

from ...models.campaigns.events import Event
from .master_detail import MasterDetailView

logger = logging.getLogger(__name__)

class EventListItem(ListItem):
    """A list item representing an event."""
    def __init__(self, event: Event):
        super().__init__()
        self.event = event

    def compose(self) -> ComposeResult:
        date_str = self.event.start_time.strftime("%m/%d %H:%M")
        yield Label(f"{date_str} - {self.event.name}")

class EventDetail(VerticalScroll):
    """Displays detailed information about an event."""
    
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.event: Optional[Event] = None

    def compose(self) -> ComposeResult:
        yield Label("Select an event to see details", id="event-detail-empty")
        yield Vertical(
            Label("", id="event-detail-title"),
            Horizontal(
                Label("Start:", classes="detail-label"),
                Label("", id="event-detail-start"),
                classes="detail-row"
            ),
            Horizontal(
                Label("Host:", classes="detail-label"),
                Label("", id="event-detail-host"),
                classes="detail-row"
            ),
            Horizontal(
                Label("Location:", classes="detail-label"),
                Label("", id="event-detail-location"),
                classes="detail-row"
            ),
            Horizontal(
                Label("Fee:", classes="detail-label"),
                Label("", id="event-detail-fee"),
                classes="detail-row"
            ),
            Horizontal(
                Label("URL:", classes="detail-label"),
                Label("", id="event-detail-url"),
                classes="detail-row"
            ),
            Label("Description:", classes="detail-label"),
            Static("", id="event-detail-description"),
            id="event-detail-content",
            classes="hidden"
        )

    def update_event(self, event: Optional[Event]) -> None:
        self.event = event
        if not event:
            self.query_one("#event-detail-empty").display = True
            self.query_one("#event-detail-content").add_class("hidden")
            return

        self.query_one("#event-detail-empty").display = False
        content = self.query_one("#event-detail-content")
        content.remove_class("hidden")

        self.query_one("#event-detail-title", Label).update(f"[bold green]{event.name}[/]")
        self.query_one("#event-detail-start", Label).update(event.start_time.strftime("%Y-%m-%d %H:%M:%S"))
        self.query_one("#event-detail-host", Label).update(event.host_name)
        self.query_one("#event-detail-location", Label).update(event.location or "N/A")
        self.query_one("#event-detail-fee", Label).update(event.fee or "Free")
        self.query_one("#event-detail-url", Label).update(event.url or "N/A")
        self.query_one("#event-detail-description", Static).update(event.description or "No description provided.")

class EventCurationView(MasterDetailView):
    """The main view for event curation."""
    
    BINDINGS = [
        Binding("a", "approve", "Approve", show=True),
        Binding("r", "reject", "Reject", show=True),
        Binding("e", "edit", "Edit", show=True),
        Binding("ctrl+r", "refresh", "Refresh", show=True),
    ]

    class EventSelected(Message):
        def __init__(self, event: Event):
            super().__init__()
            self.event = event

    def __init__(self, **kwargs: Any) -> None:
        self.event_list = ListView(id="event-list")
        self.event_detail = EventDetail(id="event-detail")
        super().__init__(master=self.event_list, detail=self.event_detail, master_width=40, **kwargs)

    async def on_mount(self) -> None:
        self.refresh_events()

    def refresh_events(self) -> None:
        """Loads events from the service and updates the list."""
        self.app.notify("Refreshing events...")
        app = cast("CocliApp", self.app)
        try:
            events = app.services.event_service.get_pending_events()
            self.event_list.clear()
            for event in events:
                self.event_list.append(EventListItem(event))
            
            if not events:
                self.event_detail.update_event(None)
                self.app.notify("No pending events found.")
        except Exception as e:
            self.app.notify(f"Error loading events: {e}", severity="error")

    @on(ListView.Selected)
    def on_event_selected(self, message: ListView.Selected) -> None:
        if isinstance(message.item, EventListItem):
            self.event_detail.update_event(message.item.event)

    def action_approve(self) -> None:
        """Approves the currently selected event."""
        selected = self.event_list.highlighted_child
        if not selected or not isinstance(selected, EventListItem):
            return

        event = selected.event
        app = cast("CocliApp", self.app)
        if app.services.event_service.approve_event(event):
            self.app.notify(f"Approved: {event.name}")
            index = self.event_list.index
            if index is not None:
                self.event_list.remove_items([index])
            # Select next or clear detail
            if self.event_list.highlighted_child:
                item = cast(EventListItem, self.event_list.highlighted_child)
                self.event_detail.update_event(item.event)
            else:
                self.event_detail.update_event(None)
        else:
            self.app.notify("Failed to approve event", severity="error")

    def action_reject(self) -> None:
        """Rejects the currently selected event."""
        selected = self.event_list.highlighted_child
        if not selected or not isinstance(selected, EventListItem):
            return

        event = selected.event
        app = cast("CocliApp", self.app)
        if app.services.event_service.reject_event(event):
            self.app.notify(f"Rejected: {event.name}")
            index = self.event_list.index
            if index is not None:
                self.event_list.remove_items([index])
            if self.event_list.highlighted_child:
                item = cast(EventListItem, self.event_list.highlighted_child)
                self.event_detail.update_event(item.event)
            else:
                self.event_detail.update_event(None)
        else:
            self.app.notify("Failed to reject event", severity="error")

    def action_edit(self) -> None:
        """Edits the currently selected event."""
        selected = self.event_list.highlighted_child
        if not selected or not isinstance(selected, EventListItem):
            return
        
        self.app.notify("Edit feature not yet implemented", severity="warning")

    def action_refresh(self) -> None:
        self.refresh_events()
