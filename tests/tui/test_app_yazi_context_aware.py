"""action_open_campaign_yazi() (the single, consolidated "y" binding,
2026-09-16) opens the visible CompanyDetail's own folder when one is
active, and the campaign root otherwise - replaces the former separate
company_detail.py "e"/Explore(Yazi) binding, which these tests used to
cover directly."""

from contextlib import nullcontext
from unittest.mock import patch

import pytest

from cocli.core.paths import paths
from cocli.tui.app import CocliApp
from cocli.tui.widgets.company_detail import CompanyDetail


@pytest.fixture
def mock_company_data():
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
    }


async def _mount(app: CocliApp, company_data: dict) -> CompanyDetail:
    detail = CompanyDetail(company_data)
    await app.query_one("#app_content").mount(detail)
    return detail


@pytest.mark.asyncio
@patch("cocli.application.company_service.get_company_details_for_view")
@patch("cocli.tui.app.time.sleep")
@patch("cocli.tui.app.subprocess.run")
@patch("cocli.tui.app.shutil.which", return_value="/usr/bin/yazi")
async def test_open_yazi_uses_company_folder_when_detail_is_active(
    mock_which,
    mock_run,
    mock_sleep,
    mock_get_details,
    mock_company_data,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(paths, "root", tmp_path)
    company_dir = tmp_path / "companies" / "test-co"
    company_dir.mkdir(parents=True)
    mock_get_details.return_value = mock_company_data

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        await _mount(app, mock_company_data)
        await pilot.pause()

        with patch.object(app, "suspend", return_value=nullcontext()) as mock_suspend:
            app.action_open_campaign_yazi()

        mock_which.assert_called_once_with("yazi")
        mock_suspend.assert_called_once()
        mock_run.assert_called_once_with(["/usr/bin/yazi", str(company_dir)], check=False)
        mock_sleep.assert_called()


@pytest.mark.asyncio
@patch("cocli.tui.app.subprocess.run")
@patch("cocli.tui.app.shutil.which", return_value="/usr/bin/yazi")
async def test_open_yazi_skips_missing_company_folder(
    mock_which, mock_run, mock_company_data, tmp_path, monkeypatch
):
    monkeypatch.setattr(paths, "root", tmp_path)

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        await _mount(app, mock_company_data)
        await pilot.pause()
        app.action_open_campaign_yazi()

        mock_which.assert_not_called()
        mock_run.assert_not_called()


@pytest.mark.asyncio
@patch("cocli.tui.app.subprocess.run")
@patch("cocli.tui.app.shutil.which", return_value=None)
async def test_open_yazi_skips_when_yazi_missing(
    mock_which, mock_run, mock_company_data, tmp_path, monkeypatch
):
    monkeypatch.setattr(paths, "root", tmp_path)
    (tmp_path / "companies" / "test-co").mkdir(parents=True)

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        await _mount(app, mock_company_data)
        await pilot.pause()
        app.action_open_campaign_yazi()

        mock_which.assert_called_once_with("yazi")
        mock_run.assert_not_called()


@pytest.mark.asyncio
@patch("cocli.tui.app.subprocess.Popen")
@patch("cocli.tui.app.subprocess.run")
@patch("cocli.tui.app.shutil.which", return_value="/usr/bin/yazi")
async def test_open_yazi_does_not_launch_nvim(
    mock_which, mock_run, mock_popen, mock_company_data, tmp_path, monkeypatch
):
    monkeypatch.setattr(paths, "root", tmp_path)
    (tmp_path / "companies" / "test-co").mkdir(parents=True)

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        await _mount(app, mock_company_data)
        await pilot.pause()

        with patch.object(app, "suspend", return_value=nullcontext()):
            with patch("cocli.tui.app.time.sleep"):
                with patch(
                    "cocli.application.company_service.get_company_details_for_view",
                    return_value=mock_company_data,
                ):
                    app.action_open_campaign_yazi()

        mock_popen.assert_not_called()
        args, _kwargs = mock_run.call_args
        assert args[0][0] == "/usr/bin/yazi"
        assert "nvim" not in args[0]


@pytest.mark.asyncio
@patch("cocli.tui.app.time.sleep")
@patch("cocli.tui.app.subprocess.run")
@patch("cocli.tui.app.shutil.which", return_value="/usr/bin/yazi")
async def test_open_yazi_uses_campaign_root_without_company_detail(
    mock_which, mock_run, mock_sleep, tmp_path, monkeypatch
):
    """No CompanyDetail active (e.g. from the Companies list, or any other
    view) - falls back to the campaign root, same as before this change."""
    from cocli.application.services import ServiceContainer

    monkeypatch.setattr(paths, "root", tmp_path)
    campaign_dir = paths.campaign("roadmap").path
    campaign_dir.mkdir(parents=True, exist_ok=True)

    app = CocliApp(services=ServiceContainer(campaign_name="roadmap"), auto_show=False)
    async with app.run_test() as pilot:
        await pilot.pause()
        with patch.object(app, "suspend", return_value=nullcontext()):
            app.action_open_campaign_yazi()

        mock_run.assert_called_once_with(["/usr/bin/yazi", str(campaign_dir)], check=False)
