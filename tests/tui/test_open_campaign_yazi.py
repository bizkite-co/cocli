from contextlib import nullcontext
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cocli.application.services import ServiceContainer
from cocli.tui.app import CocliApp


@pytest.mark.asyncio
@patch("cocli.tui.app.subprocess.run")
@patch("cocli.tui.app.shutil.which", return_value="/usr/bin/yazi")
async def test_y_opens_yazi_in_campaign_dir(
    mock_which: MagicMock, mock_run: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    campaign_dir = tmp_path / "campaigns" / "turboship"
    campaign_dir.mkdir(parents=True)

    services = ServiceContainer(campaign_name="turboship")
    app = CocliApp(services=services, auto_show=False)
    async with app.run_test() as pilot:
        await pilot.pause()
        with patch.object(app, "suspend", return_value=nullcontext()):
            app.action_open_campaign_yazi()

    mock_which.assert_called_once_with("yazi")
    mock_run.assert_called_once_with(["/usr/bin/yazi", str(campaign_dir)], check=False)


@pytest.mark.asyncio
@patch("cocli.tui.app.subprocess.run")
async def test_yazi_skipped_without_campaign(mock_run: MagicMock) -> None:
    services = ServiceContainer(campaign_name="")
    app = CocliApp(services=services, auto_show=False)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_open_campaign_yazi()
    mock_run.assert_not_called()
