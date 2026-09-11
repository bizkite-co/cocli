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
@patch("cocli.tui.widgets.company_detail.time.sleep")
@patch("cocli.tui.widgets.company_detail.subprocess.run")
@patch("cocli.tui.widgets.company_detail.shutil.which", return_value="/usr/bin/yazi")
async def test_action_open_folder_suspends_and_launches_yazi(
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
        detail = await _mount(app, mock_company_data)
        await pilot.pause()

        with patch.object(app, "suspend", return_value=nullcontext()) as mock_suspend:
            detail.action_open_folder()

        mock_which.assert_called_once_with("yazi")
        mock_suspend.assert_called_once()
        mock_run.assert_called_once_with(["/usr/bin/yazi", str(company_dir)], check=False)
        mock_sleep.assert_called()
        mock_get_details.assert_called()


@pytest.mark.asyncio
@patch("cocli.tui.widgets.company_detail.subprocess.run")
@patch("cocli.tui.widgets.company_detail.shutil.which", return_value="/usr/bin/yazi")
async def test_action_open_folder_skips_missing_folder(
    mock_which, mock_run, mock_company_data, tmp_path, monkeypatch
):
    monkeypatch.setattr(paths, "root", tmp_path)

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = await _mount(app, mock_company_data)
        await pilot.pause()
        detail.action_open_folder()

        mock_which.assert_not_called()
        mock_run.assert_not_called()


@pytest.mark.asyncio
@patch("cocli.tui.widgets.company_detail.subprocess.run")
@patch("cocli.tui.widgets.company_detail.shutil.which", return_value=None)
async def test_action_open_folder_skips_when_yazi_missing(
    mock_which, mock_run, mock_company_data, tmp_path, monkeypatch
):
    monkeypatch.setattr(paths, "root", tmp_path)
    (tmp_path / "companies" / "test-co").mkdir(parents=True)

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = await _mount(app, mock_company_data)
        await pilot.pause()
        detail.action_open_folder()

        mock_which.assert_called_once_with("yazi")
        mock_run.assert_not_called()


@pytest.mark.asyncio
@patch("cocli.tui.widgets.company_detail.subprocess.Popen")
@patch("cocli.tui.widgets.company_detail.subprocess.run")
@patch("cocli.tui.widgets.company_detail.shutil.which", return_value="/usr/bin/yazi")
async def test_action_open_folder_does_not_launch_nvim(
    mock_which, mock_run, mock_popen, mock_company_data, tmp_path, monkeypatch
):
    monkeypatch.setattr(paths, "root", tmp_path)
    (tmp_path / "companies" / "test-co").mkdir(parents=True)

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = await _mount(app, mock_company_data)
        await pilot.pause()

        with patch.object(app, "suspend", return_value=nullcontext()):
            with patch("cocli.tui.widgets.company_detail.time.sleep"):
                with patch(
                    "cocli.application.company_service.get_company_details_for_view",
                    return_value=mock_company_data,
                ):
                    detail.action_open_folder()

        mock_popen.assert_not_called()
        args, _kwargs = mock_run.call_args
        assert args[0][0] == "/usr/bin/yazi"
        assert "nvim" not in args[0]
