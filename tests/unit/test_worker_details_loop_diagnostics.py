"""_run_details_task_loop / _run_enrichment_task_loop: a browser-connectivity
break must be logged and exception-safe, not silent. Surfaced by turboship's
gm-details worker hanging indefinitely with zero log output for 6 days - the
task-level supervision in run_details_worker also never logged a crashed
worker task, making a real failure look identical to a clean session end.
See task-agent ticket
turboship-gm-details-worker-silently-dies-every-restart-never-polls."""

from unittest.mock import MagicMock, patch

import pytest
import toml

from cocli.application.worker_service import WorkerService
from cocli.core.paths import paths


def _make_service(tmp_path, campaign_name: str = "test-campaign") -> WorkerService:
    paths.root = tmp_path
    campaign_dir = tmp_path / "campaigns" / campaign_name
    campaign_dir.mkdir(parents=True)
    with open(campaign_dir / "config.toml", "w") as f:
        toml.dump({}, f)
    return WorkerService(campaign_name=campaign_name)


@pytest.mark.asyncio
async def test_details_loop_logs_entry(tmp_path, caplog):
    service = _make_service(tmp_path)
    context = MagicMock()
    context.browser = None  # falsy - breaks on the very first iteration

    with caplog.at_level("INFO", logger="cocli.application.worker_service"):
        await service._run_details_task_loop(context, MagicMock(), MagicMock(), MagicMock(), False, True)

    assert "Details worker task loop entered." in caplog.text


@pytest.mark.asyncio
async def test_details_loop_logs_disconnected_browser_instead_of_silent_break(tmp_path, caplog):
    service = _make_service(tmp_path)
    context = MagicMock()
    context.browser.is_connected.return_value = False

    with caplog.at_level("ERROR", logger="cocli.application.worker_service"):
        await service._run_details_task_loop(context, MagicMock(), MagicMock(), MagicMock(), False, True)

    assert "browser is disconnected" in caplog.text.lower()


@pytest.mark.asyncio
async def test_details_loop_logs_when_connectivity_check_itself_raises(tmp_path, caplog):
    service = _make_service(tmp_path)
    context = MagicMock()
    context.browser.is_connected.side_effect = RuntimeError("boom")

    with caplog.at_level("ERROR", logger="cocli.application.worker_service"):
        await service._run_details_task_loop(context, MagicMock(), MagicMock(), MagicMock(), False, True)

    assert "connectivity check failed" in caplog.text.lower()
    assert "boom" in caplog.text


@pytest.mark.asyncio
async def test_enrichment_loop_logs_when_connectivity_check_itself_raises(tmp_path, caplog):
    service = _make_service(tmp_path)
    context = MagicMock()
    context.browser.is_connected.side_effect = RuntimeError("boom")

    with patch("cocli.models.campaigns.campaign.Campaign.load", return_value=MagicMock()), \
         caplog.at_level("ERROR", logger="cocli.application.worker_service"):
        await service._run_enrichment_task_loop(context, MagicMock(), False, True)

    assert "connectivity check failed" in caplog.text.lower()
    assert "boom" in caplog.text
