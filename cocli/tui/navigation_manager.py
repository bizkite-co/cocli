from typing import Optional, TYPE_CHECKING
from textual.widget import Widget
import logging

if TYPE_CHECKING:
    from .app import CocliApp

logger = logging.getLogger(__name__)


class NavigationStateManager:
    """Centralized management for navigation and focus state."""

    def __init__(self, app: "CocliApp") -> None:
        self.app = app
        self.last_focused_id: Optional[str] = None

    def save_focus(self, widget: Widget) -> None:
        """Saves the current focus state."""
        if widget.id:
            self.last_focused_id = widget.id
            logger.debug(f"Saved focus: {self.last_focused_id}")

    def restore_focus(self) -> None:
        """Restores focus to the last saved widget."""
        if self.last_focused_id:
            try:
                widget = self.app.query_one(f"#{self.last_focused_id}")
                widget.focus()
                logger.debug(f"Restored focus: {self.last_focused_id}")
            except Exception as e:
                logger.error(f"Failed to restore focus: {e}")
                self.last_focused_id = None
