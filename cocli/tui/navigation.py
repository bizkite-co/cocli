from typing import Dict, Optional, Type
from textual.widget import Widget

from cocli.tui.widgets.company_list import CompanyList
from cocli.tui.widgets.company_detail import CompanyDetail
from cocli.tui.widgets.person_list import PersonList
from cocli.tui.widgets.person_detail import PersonDetail
from cocli.tui.widgets.application_view import ApplicationView, OperationsMenu
from cocli.tui.widgets.status_view import StatusView
from cocli.tui.widgets.campaign_selection import CampaignSelection

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

# --- Navigation Tree (The Branch/Leaf Registry) ---
# This serves as the 'Screaming Architecture' documentation for the TUI.
# Collection Root (e.g. CompanyList) -> Leaf Nodes (e.g. CompanyDetail)
TUI_NAV_TREE: Dict[Type[Widget], NavNode] = {
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
    # Leaf nodes are the specific category views
    OperationsMenu: NavNode(
        widget_class=OperationsMenu,
        parent_action="action_reset_view", # Focus Application sidebar
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
