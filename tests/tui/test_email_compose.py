from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import patch

import pytest

from cocli.tui.app import CocliApp
from cocli.tui.widgets.company_detail import CompanyDetail, NotesTable
from cocli.tui.widgets.email_compose_modal import EmailComposeModal


@pytest.fixture
def mock_company_data() -> dict[str, Any]:
    return {
        "company": {
            "name": "Test Co",
            "slug": "test-co",
            "domain": "test.com",
            "email": "client@test.com",
        },
        "notes": [
            {
                "timestamp": datetime(2026, 1, 2),
                "title": "Email received: Hello",
                "content": "- From: client@test.com\n- To: mark@example.com\n\nHi there",
                "file_path": "/tmp/note1.md",
            }
        ],
        "contacts": [{"name": "Pat", "role": "Owner", "email": "pat@test.com"}],
        "meetings": [],
        "tags": [],
    }


@pytest.mark.asyncio
@patch("cocli.application.company_service.get_company_details_for_view")
async def test_compose_email_opens_modal(
    mock_get_details: Any, mock_company_data: dict[str, Any], tmp_path: Any, monkeypatch: Any
) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    mock_get_details.return_value = mock_company_data
    app = CocliApp(auto_show=False)
    async with app.run_test() as driver:
        detail = CompanyDetail(mock_company_data)
        await app.query_one("#app_content").mount(detail)
        await driver.pause(0.1)
        await driver.pause()
        await driver.press("C")
        await driver.pause()
        assert isinstance(app.screen, EmailComposeModal)
        to_input = app.screen.query_one("#email-to")
        assert "client@test.com" in str(to_input.value)


@pytest.mark.asyncio
@patch("cocli.application.company_service.get_company_details_for_view")
async def test_reply_email_prefills_from_note(
    mock_get_details: Any, mock_company_data: dict[str, Any], tmp_path: Any, monkeypatch: Any
) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    mock_get_details.return_value = mock_company_data
    app = CocliApp(auto_show=False)
    async with app.run_test() as driver:
        detail = CompanyDetail(mock_company_data)
        await app.query_one("#app_content").mount(detail)
        await driver.pause(0.1)
        app.query_one("#panel-notes").focus()
        await driver.pause(0.1)
        await driver.press("i")
        assert app.query_one(NotesTable).has_focus
        await driver.press("r")
        await driver.pause()
        assert isinstance(app.screen, EmailComposeModal)
        assert "client@test.com" in str(app.screen.query_one("#email-to").value)
        assert str(app.screen.query_one("#email-subject").value).startswith("Re:")
        assert "Hi there" in app.screen.query_one("#email-body").text
