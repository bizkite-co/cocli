from unittest.mock import MagicMock, patch

import pytest

from cocli.tui.app import CocliApp
from cocli.tui.widgets.screenshot_viewer_modal import ScreenshotViewerModal


@pytest.mark.asyncio
async def test_compose_shows_missing_message_when_no_screenshot():
    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        modal = ScreenshotViewerModal(
            company_name="Test Co",
            company_slug="test-co",
            domain="test.com",
            screenshot_path=None,
        )
        await app.push_screen(modal)
        await pilot.pause()

        assert modal.query_one("#screenshot_missing")


@pytest.mark.asyncio
async def test_flag_illegitimate_confirmed_adds_exclusion():
    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        modal = ScreenshotViewerModal(
            company_name="Nemeth Family Interiors",
            company_slug="nemeth-family-interiors",
            domain="nemethfamilyinteriors.com",
            screenshot_path=None,
        )
        await app.push_screen(modal)
        await pilot.pause()

        with patch(
            "cocli.core.exclusions.ExclusionManager"
        ) as mock_manager_cls, patch(
            "cocli.core.config.get_campaign", return_value="turboship"
        ):
            mock_manager = MagicMock()
            mock_manager_cls.return_value = mock_manager

            await pilot.press("x")
            await pilot.pause()
            await pilot.press("y")
            await pilot.pause()

            mock_manager_cls.assert_called_once_with("turboship")
            mock_manager.add_exclusion.assert_called_once_with(
                slug="nemeth-family-interiors",
                domain="nemethfamilyinteriors.com",
                reason="google-maps-ad-injection",
            )


@pytest.mark.asyncio
async def test_flag_illegitimate_cancelled_does_not_add_exclusion():
    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        modal = ScreenshotViewerModal(
            company_name="Test Co",
            company_slug="test-co",
            domain="test.com",
            screenshot_path=None,
        )
        await app.push_screen(modal)
        await pilot.pause()

        with patch("cocli.core.exclusions.ExclusionManager") as mock_manager_cls:
            await pilot.press("x")
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()

            mock_manager_cls.assert_not_called()
