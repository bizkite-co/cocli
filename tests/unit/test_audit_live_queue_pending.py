"""Unit tests for cocli.commands.audit._sum_live_queue_pending(): reads
each node's own heartbeat-reported pending counts instead of trusting this
machine's local (never-synced) queues/*/pending/ directories. See
task-agent ticket
scrape-pipeline-audit-tables-pending-counts-read-stale-local-dev-machine-queue-dirs-not-live-pi-state.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from cocli.commands.audit import _fetch_live_gm_list_tile_coverage, _sum_live_queue_pending
from tests.test_audit_cluster_heartbeat import FakeS3Client

_NOW = datetime.now(timezone.utc).isoformat()


def _patched(fake_client: FakeS3Client):  # type: ignore[no-untyped-def]
    return (
        patch("cocli.core.config.load_campaign_config", return_value={}),
        patch("cocli.core.reporting.get_data_bucket_name", return_value="test-bucket"),
        patch("cocli.core.reporting.get_boto3_session", return_value=None),
        patch("cocli.core.reporting.get_s3_client", return_value=fake_client),
    )


def test_sums_pending_across_nodes_for_the_requested_campaign() -> None:
    heartbeats = {
        "cocli5x0": {
            "campaign": "turboship",
            "timestamp": _NOW,
            "queue_pending": {"gm-list": 40, "gm-details": 5, "enrichment": 100},
        },
        "cocli5x1": {
            "campaign": "turboship",
            "timestamp": _NOW,
            "queue_pending": {"gm-list": 20, "gm-details": 3, "enrichment": 50},
        },
    }
    fake_client = FakeS3Client(heartbeats)
    patches = _patched(fake_client)
    with patches[0], patches[1], patches[2], patches[3]:
        result = _sum_live_queue_pending("turboship")

    assert result == {"gm-list": 60, "gm-details": 8, "enrichment": 150}


def test_ignores_nodes_reporting_for_a_different_campaign() -> None:
    heartbeats = {
        "cocli5x0": {
            "campaign": "turboship",
            "timestamp": _NOW,
            "queue_pending": {"gm-list": 40},
        },
        "cocli5x1": {
            "campaign": "roadmap",
            "timestamp": _NOW,
            "queue_pending": {"gm-list": 999},
        },
    }
    fake_client = FakeS3Client(heartbeats)
    patches = _patched(fake_client)
    with patches[0], patches[1], patches[2], patches[3]:
        result = _sum_live_queue_pending("turboship")

    assert result == {"gm-list": 40}


def test_returns_none_when_no_node_has_published_queue_pending_yet() -> None:
    """Backward compat: a worker that hasn't been redeployed with this
    field yet must not silently look like "0 pending" - callers need to be
    able to tell "genuinely zero" apart from "no live answer available"."""
    heartbeats = {
        "cocli5x0": {
            "campaign": "turboship",
            "timestamp": _NOW,
            # no queue_pending key - pre-upgrade heartbeat shape
        },
    }
    fake_client = FakeS3Client(heartbeats)
    patches = _patched(fake_client)
    with patches[0], patches[1], patches[2], patches[3]:
        result = _sum_live_queue_pending("turboship")

    assert result is None


def test_returns_none_when_heartbeats_are_unreachable() -> None:
    with patch("cocli.core.config.load_campaign_config", side_effect=RuntimeError("no AWS creds")):
        result = _sum_live_queue_pending("turboship")

    assert result is None


def test_tile_coverage_takes_first_reporting_node_not_a_sum() -> None:
    """Unlike queue_pending, tile coverage is one shared campaign-wide
    fact - if two nodes both report for the same campaign, summing them
    would double-count it."""
    heartbeats = {
        "cocli5x0": {
            "campaign": "turboship",
            "timestamp": _NOW,
            "gm_list_tile_coverage": {
                "staged_tiles": 858,
                "tiles_with_any_result": 856,
                "tiles_with_zero_results": 2,
            },
        },
    }
    fake_client = FakeS3Client(heartbeats)
    patches = _patched(fake_client)
    with patches[0], patches[1], patches[2], patches[3]:
        result = _fetch_live_gm_list_tile_coverage("turboship")

    assert result == {"staged_tiles": 858, "tiles_with_any_result": 856, "tiles_with_zero_results": 2}


def test_tile_coverage_returns_none_when_not_yet_published() -> None:
    heartbeats = {
        "cocli5x0": {"campaign": "turboship", "timestamp": _NOW},
    }
    fake_client = FakeS3Client(heartbeats)
    patches = _patched(fake_client)
    with patches[0], patches[1], patches[2], patches[3]:
        result = _fetch_live_gm_list_tile_coverage("turboship")

    assert result is None
