from typing import Optional, Type, TYPE_CHECKING
from textual.widget import Widget
from datetime import datetime

# Lazy imports for widgets to avoid circular dependencies
if TYPE_CHECKING:
    pass

class NavNode:
    """
    Represents a node in the TUI navigation tree.
    This provides a declarative way to map UI components to their functional hierarchy,
    aligning with the Cocli Data Ordinance.
    """
    def __init__(
        self, 
        widget_class: Type[Widget], 
        parent_action: Optional[str] = None, 
        root_widget: Optional[Type[Widget]] = None,
        model_type: Optional[str] = None,
        is_branch_root: bool = False
    ):
        self.widget_class = widget_class
        self.parent_action = parent_action
        # The 'root_widget' is the branch root (Search/List or Sidebar)
        self.root_widget = root_widget or widget_class
        self.model_type = model_type
        # If true, alt+s while focused on this will try to focus its sidebar/input
        self.is_branch_root = is_branch_root

# --- Process Tracking ---
class ProcessRun:
    """Tracks a single execution of a background task."""
    def __init__(self, op_id: str, title: str):
        self.op_id = op_id
        self.title = title
        self.start_time = datetime.now()
        self.end_time: Optional[datetime] = None
        self.status: str = "running"
        self.message: str = ""

# The actual mapping will be initialized in app.py to ensure all widgets are fully loaded
# and avoid any module-level circularity.
