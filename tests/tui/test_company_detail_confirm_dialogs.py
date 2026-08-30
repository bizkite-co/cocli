"""Four confirm-dialog / dismiss-await bugs found and fixed 2026-08-30 in
company_detail.py: `confirm = await self.app.push_screen(ConfirmScreen(...))`
(without wait_for_dismiss) always returns None regardless of what the user
presses - confirmed empirically, not just by reading code - so `if confirm:`
never used to fire. action_delete_company, action_toggle_to_call, and
action_delete_note all relied on this. action_call_company had a related
but different bug: it awaited the call-log modal's *mount*, not its
*dismissal*, so the post-call refresh fired before the user had actually
logged anything.

The fix in all four cases is push_screen_wait (the correctly-typed way to
await a screen's real dismiss value/dismissal) - which requires an active
Textual worker, so each bound action is now a sync dispatcher that hands
the real work to self.app.run_worker(...), matching the pattern this file
already used for action_re_enqueue_scrape/action_re_enrich.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cocli.core.paths import paths
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
            "phone_1": "5551234567",
        },
        "contacts": [],
        "meetings": [],
        "notes": [
            {"title": "Note A", "content": "hello", "file_path": str(tmp_path / "note-a.md")}
        ],
        "website_data": None,
        "tags": [],
        "enrichment_path": str(enrichment_dir / "website.md"),
    }


async def _mount(app: CocliApp, pilot, company_data) -> CompanyDetail:
    detail = CompanyDetail(company_data)
    await app.query_one("#app_content").mount(detail)
    await pilot.pause()  # on_mount() focuses panel_info
    return detail


# ---------------------------------------------------------------------------
# action_delete_company
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_company_confirmed_deletes_directory(mock_company_data, tmp_path):
    company_dir = tmp_path / "companies" / "test-co"
    company_dir.mkdir(parents=True, exist_ok=True)
    (company_dir / "marker.txt").write_text("x")

    with patch.object(paths, "root", tmp_path):
        app = CocliApp(auto_show=False)
        async with app.run_test() as pilot:
            await _mount(app, pilot, mock_company_data)

            with patch("cocli.core.cache.build_cache"), patch.object(
                app, "action_show_companies", MagicMock()
            ):
                await pilot.press("D")
                await pilot.pause()
                await pilot.press("y")
                await pilot.pause()

    assert not company_dir.exists()


@pytest.mark.asyncio
async def test_delete_company_cancelled_keeps_directory(mock_company_data, tmp_path):
    company_dir = tmp_path / "companies" / "test-co"
    company_dir.mkdir(parents=True, exist_ok=True)
    (company_dir / "marker.txt").write_text("x")

    with patch.object(paths, "root", tmp_path):
        app = CocliApp(auto_show=False)
        async with app.run_test() as pilot:
            await _mount(app, pilot, mock_company_data)

            await pilot.press("D")
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()

    assert company_dir.exists()
    assert (company_dir / "marker.txt").exists()


# ---------------------------------------------------------------------------
# action_toggle_to_call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_toggle_to_call_removes_when_confirmed(mock_company_data, tmp_path):
    fake_company = MagicMock(slug="test-co", domain="test.com", name="Test Co")
    task_path = tmp_path / "to_call_task.usv"
    task_path.write_text("dummy")

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        await _mount(app, pilot, mock_company_data)

        with patch(
            "cocli.tui.widgets.company_detail.Company.get", return_value=fake_company
        ), patch(
            "cocli.models.campaigns.queues.to_call.ToCallTask.get_local_path",
            return_value=task_path,
        ), patch("cocli.core.config.get_campaign", return_value="turboship"):
            await pilot.press("t")
            await pilot.pause()
            await pilot.press("y")
            await pilot.pause()

    assert not task_path.exists()


@pytest.mark.asyncio
async def test_toggle_to_call_cancelled_keeps_task(mock_company_data, tmp_path):
    fake_company = MagicMock(slug="test-co", domain="test.com", name="Test Co")
    task_path = tmp_path / "to_call_task.usv"
    task_path.write_text("dummy")

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        await _mount(app, pilot, mock_company_data)

        with patch(
            "cocli.tui.widgets.company_detail.Company.get", return_value=fake_company
        ), patch(
            "cocli.models.campaigns.queues.to_call.ToCallTask.get_local_path",
            return_value=task_path,
        ), patch("cocli.core.config.get_campaign", return_value="turboship"):
            await pilot.press("t")
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()

    assert task_path.exists()


# ---------------------------------------------------------------------------
# action_delete_note
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_note_confirmed_deletes_file(mock_company_data, tmp_path):
    note_path = Path(mock_company_data["notes"][0]["file_path"])
    note_path.write_text("hello")

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = await _mount(app, pilot, mock_company_data)
        detail.panel_notes.focus()
        await pilot.pause()

        await pilot.press("d")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()

    assert not note_path.exists()


@pytest.mark.asyncio
async def test_delete_note_cancelled_keeps_file(mock_company_data, tmp_path):
    note_path = Path(mock_company_data["notes"][0]["file_path"])
    note_path.write_text("hello")

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = await _mount(app, pilot, mock_company_data)
        detail.panel_notes.focus()
        await pilot.pause()

        await pilot.press("d")
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()

    assert note_path.exists()


# ---------------------------------------------------------------------------
# action_call_company
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_company_refreshes_only_after_modal_dismissed(mock_company_data):
    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = await _mount(app, pilot, mock_company_data)

        call_order: list[str] = []

        async def fake_push_screen_wait(screen):
            call_order.append("modal_dismissed")
            return True

        with patch(
            "cocli.tui.widgets.company_detail.open_url", return_value=True
        ), patch.object(
            app, "push_screen_wait", AsyncMock(side_effect=fake_push_screen_wait)
        ), patch.object(
            detail, "refresh_notes_data", MagicMock(side_effect=lambda: call_order.append("refresh_notes"))
        ), patch.object(
            detail, "refresh_meetings_data", MagicMock(side_effect=lambda: call_order.append("refresh_meetings"))
        ), patch.object(
            detail, "_refresh_info_table", MagicMock(side_effect=lambda: call_order.append("refresh_info"))
        ):
            await pilot.press("p")
            await pilot.pause()

    assert call_order == [
        "modal_dismissed",
        "refresh_notes",
        "refresh_meetings",
        "refresh_info",
    ]
