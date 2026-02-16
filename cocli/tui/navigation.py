from typing import Dict, Optional, Type
from textual.widget import Widget

from cocli.tui.widgets.company_list import CompanyList
from cocli.tui.widgets.company_detail import CompanyDetail
from cocli.tui.widgets.person_list import PersonList
from cocli.tui.widgets.person_detail import PersonDetail

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
        model_type: Optional[str] = None
    ):
        self.widget_class = widget_class
        self.parent_action = parent_action
        # The 'root_widget' is the branch root (usually a Search/List widget)
        self.root_widget = root_widget or widget_class
        # Mapping to Data Ordinance collection names
        self.model_type = model_type

# --- Navigation Tree (The Branch/Leaf Registry) ---
# This serves as the 'Screaming Architecture' documentation for the TUI.
# It explicitly maps Leaf nodes (Details) to their Branch Roots (Search).
# Collection Root (e.g. CompanyList) -> Leaf Nodes (e.g. CompanyDetail)
TUI_NAV_TREE: Dict[Type[Widget], NavNode] = {
    CompanyDetail: NavNode(
        widget_class=CompanyDetail,
        parent_action="action_show_companies",
        root_widget=CompanyList,
        model_type="companies"
    ),
    PersonDetail: NavNode(
        widget_class=PersonDetail,
        parent_action="action_show_people",
        root_widget=PersonList,
        model_type="people"
    ),
    CompanyList: NavNode(
        widget_class=CompanyList,
        model_type="companies"
    ),
    PersonList: NavNode(
        widget_class=PersonList,
        model_type="people"
    )
}
