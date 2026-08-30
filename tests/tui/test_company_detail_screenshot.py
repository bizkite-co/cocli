"""CompanyDetail shows the captured website screenshot (see
cocli/models/companies/website.py's screenshot_bytes field) inline,
always visible under the metadata panel - not behind a keypress/modal.
Mark, 2026-08-30: "It should just show it under the metadata. We don't
need a shortcut key. We've got a little room to just show it."
"""

from pathlib import Path

import pytest

from cocli.tui.app import CocliApp
from cocli.tui.widgets.company_detail import CompanyDetail


@pytest.fixture
def mock_company_data(tmp_path: Path):
    enrichment_dir = tmp_path / "companies" / "test-co" / "enrichments"
    enrichment_dir.mkdir(parents=True)
    return {
        "company": {
            "name": "Test Co",
            "slug": "test-co",
            "domain": "test.com",
        },
        "contacts": [],
        "meetings": [],
        "notes": [],
        "website_data": None,
        "tags": [],
        "enrichment_path": str(enrichment_dir / "website.md"),
    }


def _write_real_png(path: Path) -> None:
    from PIL import Image

    Image.new("RGB", (4, 4), color=(255, 0, 0)).save(path, format="PNG")


@pytest.mark.asyncio
async def test_shows_image_widget_when_screenshot_exists(mock_company_data):
    enrichment_dir = Path(mock_company_data["enrichment_path"]).parent
    _write_real_png(enrichment_dir / "screenshot.png")

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = CompanyDetail(mock_company_data)
        await app.query_one("#app_content").mount(detail)
        await pilot.pause()

        from textual_image.widget import AutoImage

        panel = detail.query_one("#screenshot-panel")
        assert len(list(panel.query(AutoImage))) == 1


@pytest.mark.asyncio
async def test_shows_missing_message_when_no_screenshot(mock_company_data):
    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = CompanyDetail(mock_company_data)
        await app.query_one("#app_content").mount(detail)
        await pilot.pause()

        from textual.widgets import Label
        from textual_image.widget import AutoImage

        panel = detail.query_one("#screenshot-panel")
        assert len(list(panel.query(AutoImage))) == 0
        label = panel.query_one(Label)
        assert "No screenshot" in str(label.content)


@pytest.mark.asyncio
async def test_shows_missing_message_when_no_enrichment_path(mock_company_data):
    mock_company_data["enrichment_path"] = None
    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = CompanyDetail(mock_company_data)
        await app.query_one("#app_content").mount(detail)
        await pilot.pause()

        from textual_image.widget import AutoImage

        panel = detail.query_one("#screenshot-panel")
        assert len(list(panel.query(AutoImage))) == 0
