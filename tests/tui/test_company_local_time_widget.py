from __future__ import annotations

import pytest
from typing import Any
from unittest.mock import patch

from textual.app import App, ComposeResult

from cocli.models.companies.company import Company
from cocli.tui.app import CocliApp
from cocli.tui.widgets.company_detail import CompanyDetail
from cocli.tui.widgets.company_local_time import CompanyLocalTime


class LocalTimeTestApp(App):
    def __init__(self, widget: CompanyLocalTime):
        super().__init__()
        self.widget = widget

    def compose(self) -> ComposeResult:
        yield self.widget


@pytest.mark.asyncio
async def test_company_local_time_resolves_place_and_renders():
    data = {
        "company": {
            "name": "Acme Widgets",
            "slug": "acme-widgets",
            "state": "CA",
            "city": "Los Angeles",
        }
    }
    widget = CompanyLocalTime(company=data)
    app = LocalTimeTestApp(widget)
    async with app.run_test():
        rendered = widget.get_time_markup()
        assert "bold green" in rendered
        assert "Los Angeles, CA" in rendered
        assert str(widget._place.tz) == "America/Los_Angeles"


@pytest.mark.asyncio
async def test_company_local_time_set_company_updates_place():
    data_ca = {"company": {"name": "CA Co", "state": "CA", "city": "San Francisco"}}
    data_ny = {"company": {"name": "NY Co", "state": "NY", "city": "New York"}}

    widget = CompanyLocalTime(company=data_ca)
    app = LocalTimeTestApp(widget)
    async with app.run_test():
        assert str(widget._place.tz) == "America/Los_Angeles"

        widget.set_company(data_ny)
        assert str(widget._place.tz) == "America/New_York"
        assert "New York, NY" in widget.get_time_markup()


@pytest.mark.asyncio
async def test_company_detail_mounts_local_time_widget():
    company_data: dict[str, Any] = {
        "company": {
            "name": "Test Energy",
            "slug": "test-energy",
            "state": "TX",
            "city": "Dallas",
        },
        "contacts": [],
        "meetings": [],
        "notes": [],
    }

    app = CocliApp(auto_show=False)
    async with app.run_test(size=(120, 40)) as pilot:
        detail = CompanyDetail(company_data)
        await app.query_one("#app_content").mount(detail)
        await pilot.pause()

        clock = app.query_one("#company_local_time", CompanyLocalTime)
        assert clock is not None
        assert "Dallas, TX" in clock.get_time_markup()
        assert str(clock._place.tz) == "America/Chicago"


@pytest.mark.asyncio
@patch("cocli.tui.widgets.call_log_modal.get_campaign", return_value="roadmap")
async def test_call_log_modal_uses_company_local_time(_mock_campaign: Any, tmp_path: Any, monkeypatch: Any):
    from cocli.core.paths import paths
    from cocli.tui.widgets.call_log_modal import CallLogModal

    monkeypatch.setattr(paths, "root", tmp_path)

    co = Company(name="Pacific Health", slug="pacific-health", state="WA", city="Seattle")
    co.save()

    app = CocliApp(auto_show=False)
    async with app.run_test() as driver:
        modal = CallLogModal(company_slug="pacific-health", phone="555-123-4567")
        app.push_screen(modal)
        await driver.pause()

        clock = modal.query_one("#company_local_time", CompanyLocalTime)
        assert clock is not None
        assert str(clock._place.tz) == "America/Los_Angeles"
        assert "Seattle, WA" in clock.get_time_markup()
