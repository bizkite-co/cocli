"""CompanyDetail's Meetings panel surfaces pending to-call callbacks and
follow-up tasks as synthetic rows - the "why can't I see Jimmy Jean's
scheduled callback anywhere on his page" gap (Mark, 2026-09-17)."""

from __future__ import annotations

from datetime import datetime, timedelta, UTC
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from cocli.core.paths import paths
from cocli.tui.app import CocliApp
from cocli.tui.widgets.company_detail import CompanyDetail, MeetingsTable


def _company_data(callback_at: str | None = None) -> dict[str, Any]:
    return {
        "company": {
            "name": "Jimmy Jean Insurance",
            "slug": "jimmy-jean-insurance",
            "domain": "jimmyjeaninsurance.com",
            "callback_at": callback_at,
        },
        "notes": [],
        "contacts": [],
        "meetings": [],
        "tags": [],
    }


def _cell_texts(table: MeetingsTable) -> list[str]:
    texts = []
    for row_key in table.rows:
        row = table.get_row(row_key)
        texts.append(str(row[1]))
    return texts


@pytest.mark.asyncio
@patch("cocli.core.config.get_campaign", return_value="roadmap")
@patch("cocli.application.company_service.get_company_details_for_view")
async def test_scheduled_future_callback_shows_as_yellow_row(
    mock_get_details: Any, _mock_campaign: Any, tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(paths, "root", tmp_path)
    future = (datetime.now(UTC) + timedelta(days=6)).isoformat()
    company_data = _company_data(callback_at=future)
    mock_get_details.return_value = company_data

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = CompanyDetail(company_data)
        await app.query_one("#app_content").mount(detail)
        await pilot.pause()

        table = app.query_one(MeetingsTable)
        texts = _cell_texts(table)
        assert any("Callback scheduled" in t for t in texts)
        assert not any("overdue" in t.lower() for t in texts)


@pytest.mark.asyncio
@patch("cocli.core.config.get_campaign", return_value="roadmap")
@patch("cocli.application.company_service.get_company_details_for_view")
async def test_overdue_callback_shows_as_overdue_row(
    mock_get_details: Any, _mock_campaign: Any, tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(paths, "root", tmp_path)
    past = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    company_data = _company_data(callback_at=past)
    mock_get_details.return_value = company_data

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = CompanyDetail(company_data)
        await app.query_one("#app_content").mount(detail)
        await pilot.pause()

        table = app.query_one(MeetingsTable)
        texts = _cell_texts(table)
        assert any("Callback overdue" in t for t in texts)


@pytest.mark.asyncio
@patch("cocli.core.config.get_campaign", return_value="roadmap")
@patch("cocli.application.company_service.get_company_details_for_view")
async def test_no_callback_shows_no_synthetic_row(
    mock_get_details: Any, _mock_campaign: Any, tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(paths, "root", tmp_path)
    company_data = _company_data(callback_at=None)
    mock_get_details.return_value = company_data

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = CompanyDetail(company_data)
        await app.query_one("#app_content").mount(detail)
        await pilot.pause()

        table = app.query_one(MeetingsTable)
        texts = _cell_texts(table)
        assert not any("Callback" in t for t in texts)


@pytest.mark.asyncio
@patch("cocli.core.config.get_campaign", return_value="roadmap")
@patch("cocli.application.company_service.get_company_details_for_view")
async def test_pending_follow_up_task_shows_as_synthetic_row(
    mock_get_details: Any, _mock_campaign: Any, tmp_path: Path, monkeypatch: Any
) -> None:
    from cocli.application.follow_up_service import FollowUpService

    monkeypatch.setattr(paths, "root", tmp_path)
    company_data = _company_data(callback_at=None)
    mock_get_details.return_value = company_data

    service = FollowUpService("roadmap")
    service.add_follow_up(
        company_slug="jimmy-jean-insurance",
        domain="jimmyjeaninsurance.com",
        scheduled_at=datetime.now(UTC) + timedelta(days=1),
        format="email",
        template_id="email_02_product_overview.md",
        initiative="rta",
    )

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = CompanyDetail(company_data)
        await app.query_one("#app_content").mount(detail)
        await pilot.pause()

        table = app.query_one(MeetingsTable)
        texts = _cell_texts(table)
        assert any("Follow-up: email" in t for t in texts)
        assert any("email_02_product_overview.md" in t for t in texts)
