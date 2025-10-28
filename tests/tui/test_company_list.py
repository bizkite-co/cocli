import pytest
from textual.app import App, ComposeResult
from textual.widgets import ListView, ListItem, Label
from textual.containers import VerticalScroll
from unittest.mock import patch

from cocli.tui.screens.company_list import CompanyList
from cocli.utils.textual_utils import sanitize_id # New import

# Mock the Company class and its get_all method
class MockCompany:
    def __init__(self, name: str, slug: str):
        self.name = name
        self.slug = slug # Add slug attribute

    @classmethod
    def get_all(cls):
        return [
            cls(name="Company A", slug="company-a"),
            cls(name="Company B", slug="company-b"),
            cls(name="Company C", slug="company-c"),
            cls(name="1st Company", slug="1st-company"), # Add a company with a slug starting with a number
        ]

class CompanyListTestApp(App[None]):
    """A test app for the CompanyList screen."""

    SCREENS = {"company_list": CompanyList}

    def on_mount(self) -> None:
        self.push_screen("company_list")

@pytest.mark.asyncio
async def test_company_list_display_companies():
    """Test that the CompanyList screen displays companies correctly."""
    with patch('cocli.tui.screens.company_list.Company', new=MockCompany):
        app = CompanyListTestApp()
        async with app.run_test() as driver:
            # Get the CompanyList screen
            company_list_screen = app.get_screen("company_list")
            assert isinstance(company_list_screen, CompanyList)

            # Find the ListView widget
            list_view = company_list_screen.query_one(ListView)
            assert isinstance(list_view, ListView)

            # Assert that the ListView contains the expected company slugs
            expected_company_slugs = [
                sanitize_id("company-a"),
                sanitize_id("company-b"),
                sanitize_id("company-c"),
                sanitize_id("1st-company"), # Sanitize the slug starting with a number
            ]
            displayed_items = [item.id for item in list_view.children if isinstance(item, ListItem)]
            
            assert sorted(displayed_items) == sorted(expected_company_slugs)
