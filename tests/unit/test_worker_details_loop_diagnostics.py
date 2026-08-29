"""_run_details_task_loop / _run_enrichment_task_loop: a browser-connectivity
break must be logged and exception-safe, not silent. Surfaced by turboship's
gm-details worker hanging indefinitely with zero log output for 6 days - the
task-level supervision in run_details_worker also never logged a crashed
worker task, making a real failure look identical to a clean session end.

The actual root cause turned out to be _rebalance_workers() itself: a
gossip-pushed [prospecting.scaling.cocli5x0] with gm-details=0 silently
excluded it from every rebalance, on every hourly restart, for 6+ days -
not a hang at all. _rebalance_workers() never logged anything a human or
`cocli audit cluster`'s "Starting worker:" parser could see, so the audit
tool kept showing the stale boot-time worker count. See task-agent ticket
turboship-gm-details-worker-silently-dies-every-restart-never-polls.

The reason the bad scaling value got stuck in the first place - a
_watch_remote_config() watermark bug that let a stale gossip broadcast
replay forever - is a separate, general-purpose bug and is covered in its
own ticket/test file: see task-agent ticket
gossip-config-broadcasts-never-expire-stale-scaling-replayed-forever-no-cross-campaign-guard
and tests/unit/test_worker_remote_config_watch.py."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

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


async def _fake_worker_coro(self: WorkerService, *args: object, **kwargs: object) -> None:
    await asyncio.sleep(100)


@pytest.mark.asyncio
async def test_rebalance_logs_starting_worker_for_surviving_types(tmp_path, caplog):
    fake_config = {
        "prospecting": {"scaling": {"testnode": {"gm-list": 1, "gm-details": 2, "enrichment": 2}}},
        "aws": {"iot_profiles": ["test-iot"]},
    }
    with patch("cocli.core.paths.paths.root", tmp_path), \
         patch("cocli.application.worker_service.load_campaign_config", return_value=fake_config):
        supervisor = WorkerService(campaign_name="test_campaign", processed_by="testnode")

    with patch("cocli.application.worker_service.load_campaign_config", return_value=fake_config), \
         patch.object(WorkerService, "run_worker", _fake_worker_coro), \
         patch.object(WorkerService, "run_details_worker", _fake_worker_coro), \
         patch.object(WorkerService, "run_enrichment_worker", _fake_worker_coro), \
         caplog.at_level("INFO", logger="cocli.application.worker_service"):
        await supervisor._rebalance_workers()

    assert "Starting worker: testnode-gm-list (type=gm-list, workers=1)" in caplog.text
    assert "Starting worker: testnode-gm-details (type=gm-details, workers=2)" in caplog.text
    assert "Starting worker: testnode-enrichment (type=enrichment, workers=2)" in caplog.text


@pytest.mark.asyncio
async def test_rebalance_logs_zero_worker_line_for_excluded_type(tmp_path, caplog):
    # The exact incident: gm-details=0 must be visible, not silent.
    fake_config = {
        "prospecting": {"scaling": {"testnode": {"gm-list": 1, "gm-details": 0, "enrichment": 2}}},
        "aws": {"iot_profiles": ["test-iot"]},
    }
    with patch("cocli.core.paths.paths.root", tmp_path), \
         patch("cocli.application.worker_service.load_campaign_config", return_value=fake_config):
        supervisor = WorkerService(campaign_name="test_campaign", processed_by="testnode")

    with patch("cocli.application.worker_service.load_campaign_config", return_value=fake_config), \
         patch.object(WorkerService, "run_worker", _fake_worker_coro), \
         patch.object(WorkerService, "run_enrichment_worker", _fake_worker_coro), \
         caplog.at_level("INFO", logger="cocli.application.worker_service"):
        await supervisor._rebalance_workers()

    assert "gm-details scaled to 0 on testnode" in caplog.text
    assert "Starting worker: testnode-gm-details (type=gm-details, workers=0)" in caplog.text


def _make_ready_context() -> MagicMock:
    context = MagicMock()
    context.browser.is_connected.return_value = True
    context.new_page = AsyncMock(return_value=MagicMock(close=AsyncMock()))
    return context


@pytest.mark.asyncio
async def test_details_loop_nacks_instead_of_acking_an_empty_result(tmp_path, caplog):
    """Production incident (2026-08): GoogleMapsDetailsProcessor.process()
    returns None on both "no data found" and a swallowed internal exception -
    neither path ever reaches add_to_wal(). The old code acked regardless,
    permanently marking the task complete with no WAL entry and no retry.
    21 place_ids were found stuck in exactly this state via `cocli index
    trace`. ack() must never fire when process() produced nothing."""
    service = _make_service(tmp_path)
    context = _make_ready_context()

    fake_task = MagicMock(place_id="ChIJfake", campaign_name="test-campaign", force_refresh=False)
    gm_list_item_queue = MagicMock()
    gm_list_item_queue.poll.return_value = [fake_task]
    enrichment_queue = MagicMock()

    with patch(
        "cocli.application.processors.google_maps.GoogleMapsDetailsProcessor.process",
        new=AsyncMock(return_value=None),
    ), caplog.at_level("WARNING", logger="cocli.application.worker_service"):
        await service._run_details_task_loop(
            context, gm_list_item_queue, enrichment_queue, MagicMock(), False, True
        )

    gm_list_item_queue.nack.assert_called_once_with(fake_task)
    gm_list_item_queue.ack.assert_not_called()
    enrichment_queue.push.assert_not_called()
    assert "no prospect data" in caplog.text.lower()


@pytest.mark.asyncio
async def test_enrichment_loop_nacks_instead_of_acking_a_failed_scrape(tmp_path, caplog):
    """WebsiteScraper.run() catches its own Timeout/Exception internally and
    always returns a Website with `.error` set rather than raising - so the
    old code's unconditional ack() marked every failed/timed-out scrape
    "completed" with nothing to ever retry it. Same shape as the gm-details
    fix above; mirrored here for enrichment."""
    service = _make_service(tmp_path)
    context = _make_ready_context()

    fake_task = MagicMock(company_slug="acme-flooring", domain="acme-flooring.com", force_refresh=False)
    enrichment_queue = MagicMock()
    enrichment_queue.poll.return_value = [fake_task]

    from cocli.models.companies.website import Website

    failed_website = Website(url="acme-flooring.com", error="Timeout", error_category="timeout")

    with patch("cocli.models.campaigns.campaign.Campaign.load", return_value=MagicMock()), \
         patch("cocli.core.enrichment.enrich_company_website", new=AsyncMock(return_value=failed_website)), \
         caplog.at_level("WARNING", logger="cocli.application.worker_service"):
        await service._run_enrichment_task_loop(context, enrichment_queue, False, True)

    enrichment_queue.nack.assert_called_once_with(fake_task)
    enrichment_queue.ack.assert_not_called()
    assert "enrichment scrape failed" in caplog.text.lower()


@pytest.mark.asyncio
async def test_enrichment_loop_acks_on_real_success(tmp_path):
    """The success path must be unchanged: a clean scrape with no error
    still acks."""
    service = _make_service(tmp_path)
    context = _make_ready_context()

    fake_task = MagicMock(company_slug="acme-flooring", domain="acme-flooring.com", force_refresh=False)
    enrichment_queue = MagicMock()
    enrichment_queue.poll.return_value = [fake_task]

    from cocli.models.companies.website import Website

    good_website = Website(url="acme-flooring.com", description="A real flooring contractor.")

    with patch("cocli.models.campaigns.campaign.Campaign.load", return_value=MagicMock()), \
         patch("cocli.core.enrichment.enrich_company_website", new=AsyncMock(return_value=good_website)):
        await service._run_enrichment_task_loop(context, enrichment_queue, False, True)

    enrichment_queue.ack.assert_called_once_with(fake_task)
    enrichment_queue.nack.assert_not_called()


@pytest.mark.asyncio
async def test_details_loop_acks_and_pushes_enrichment_on_real_success(tmp_path):
    """The success path must be unchanged: a real prospect with a domain
    still acks and still pushes to the enrichment queue."""
    service = _make_service(tmp_path)
    context = _make_ready_context()

    fake_task = MagicMock(
        place_id="ChIJfake", campaign_name="test-campaign", force_refresh=False, job_run_id=None
    )
    gm_list_item_queue = MagicMock()
    gm_list_item_queue.poll.return_value = [fake_task]
    enrichment_queue = MagicMock()

    fake_prospect = MagicMock(domain="example.com", name="Example Co")

    with patch(
        "cocli.application.processors.google_maps.GoogleMapsDetailsProcessor.process",
        new=AsyncMock(return_value=fake_prospect),
    ):
        await service._run_details_task_loop(
            context, gm_list_item_queue, enrichment_queue, MagicMock(), False, True
        )

    gm_list_item_queue.ack.assert_called_once_with(fake_task)
    gm_list_item_queue.nack.assert_not_called()
    enrichment_queue.push.assert_called_once()
