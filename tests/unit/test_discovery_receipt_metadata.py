# POLICY: frictionless-data-policy-enforcement
import json
import pytest

from cocli.application.processors.gm_list import GmListProcessor
from cocli.models.campaigns.queues.gm_list import ScrapeTask
from cocli.models.campaigns.indexes.google_maps_list_item import GoogleMapsListItem


@pytest.mark.asyncio
async def test_receipt_metadata_persistence(tmp_path, monkeypatch):
    # 1. Setup paths to use a temporary directory
    # We need to monkeypatch cocli.core.paths.paths.root to point to tmp_path
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    campaign = "test_campaign"
    campaign_dir = tmp_path / "campaigns" / campaign
    campaign_dir.mkdir(parents=True)

    # 2. Mock a ScrapeTask
    task = ScrapeTask(
        latitude=25.0,
        longitude=-80.0,
        zoom=14,
        search_phrase="test phrase",
        campaign_name=campaign,
        tile_id="25.0_-80.0",
        ack_token="test_token",
    )

    # 3. Mock results
    items = [
        GoogleMapsListItem(
            place_id="ChIJ123456789012345678901234",  # 28 chars (within max 29)
            name="Test Business",
            company_slug="test-business",
            gmb_url="https://google.com/maps/place/Test+Business/",
        )
    ]

    # 4. Define metadata
    test_metadata = {
        "user_agent": "TestAgent/1.0",
        "common_headers": {"X-Test": "Value"},
        "browser_settings": {"headless": True},
    }

    # 5. Process results
    processor = GmListProcessor(processed_by="test-worker")
    await processor.process_results(task, items, metadata=test_metadata)

    # 6. Verify Receipt
    # Path: campaigns/{campaign}/queues/gm-list/completed/results/{shard}/{lat}/{lon}/{phrase}.json
    receipt_path = (
        tmp_path
        / "campaigns"
        / campaign
        / "queues"
        / "gm-list"
        / "completed"
        / "results"
        / "2"
        / "25.0"
        / "-80.0"
        / "test-phrase.json"
    )

    assert receipt_path.exists(), f"Receipt not found at {receipt_path}"

    with open(receipt_path, "r") as f:
        data = json.load(f)

    assert "metadata" in data
    assert data["metadata"]["user_agent"] == "TestAgent/1.0"
    assert data["metadata"]["browser_settings"]["headless"] is True
    assert data["result_count"] == 1
    assert data["worker_id"] == "test-worker"
