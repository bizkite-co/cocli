import pytest
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Header, Footer

from cocli.tui.base import CocliPanel
from cocli.tui.widgets.company_detail import DetailPanel, QuadrantTable
from cocli.tui.widgets.company_list import CompanyList
from cocli.tui.widgets.company_preview import CompanyPreview
from cocli.tui.widgets.template_list import TemplateList
from cocli.tui.widgets.person_detail import PersonDetail
from cocli.tui.widgets.person_list import PersonList
from cocli.application.services import ServiceContainer


class HeaderPreventionApp(App[None]):
    def __init__(self, services=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.services = services or ServiceContainer()

    def compose(self) -> ComposeResult:
        yield Footer()
        yield Container(id="app_content")


@pytest.mark.asyncio
async def test_border_title_suppression_on_cocli_panels():
    """Verify that border_title is strictly empty and setting title reactive property does not leak border_title."""
    panel = CocliPanel(panel_title="TEST PANEL")
    assert panel.border_title == ""

    # Test setting title reactive property
    panel.title = "NEW TITLE"
    assert panel.border_title == ""


@pytest.mark.asyncio
async def test_detail_panel_and_quadrant_table_border_title():
    """Verify DetailPanel and QuadrantTable maintain empty border_title."""
    table = QuadrantTable()
    assert table.border_title == ""
    table.title = "TABLE TITLE"
    assert table.border_title == ""

    panel = DetailPanel(title="COMPANY INFO", child=table, id="panel-info")
    assert panel.border_title == ""
    panel.title = "PANEL TITLE"
    assert panel.border_title == ""


@pytest.mark.asyncio
async def test_search_view_panes_border_title():
    """Verify search view panes maintain empty border_title."""
    c_list = CompanyList()
    c_preview = CompanyPreview()
    t_list = TemplateList()

    assert c_list.border_title == ""
    assert c_preview.border_title == ""
    assert t_list.border_title == ""

    c_list.title = "SEARCH"
    c_preview.title = "PREVIEW"
    t_list.title = "TEMPLATES"

    assert c_list.border_title == ""
    assert c_preview.border_title == ""
    assert t_list.border_title == ""


@pytest.mark.asyncio
async def test_person_detail_and_list_no_duplicate_footer():
    """Verify PersonDetail and PersonList do not yield duplicate Header/Footer when mounted."""
    app = HeaderPreventionApp()
    
    async with app.run_test() as driver:
        content = app.query_one("#app_content", Container)
        
        person_detail = PersonDetail(person_slug="test-person")
        await content.mount(person_detail)
        await driver.pause(0.1)

        # Check Footers in the entire app: should be exactly 1 (the root app Footer)
        footers = list(app.query(Footer))
        headers = list(app.query(Header))

        assert len(footers) == 1, f"Expected 1 Footer, found {len(footers)}"
        assert len(headers) == 0, f"Expected 0 Headers, found {len(headers)}"

        person_list = PersonList()
        await content.mount(person_list)
        await driver.pause(0.1)

        footers = list(app.query(Footer))
        headers = list(app.query(Header))

        assert len(footers) == 1, f"Expected 1 Footer, found {len(footers)}"
        assert len(headers) == 0, f"Expected 0 Headers, found {len(headers)}"
