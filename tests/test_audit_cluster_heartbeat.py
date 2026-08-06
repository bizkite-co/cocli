import json
from typing import Any, Dict, List
from unittest.mock import patch

from rich.console import Console

import cocli.commands.audit as audit_module
from cocli.commands.audit import _audit_cluster_from_heartbeats


class FakePaginator:
    def __init__(self, pages_by_prefix: Dict[str, List[Dict[str, Any]]]) -> None:
        self._pages_by_prefix = pages_by_prefix

    def paginate(self, Bucket: str, Prefix: str) -> List[Dict[str, Any]]:
        return self._pages_by_prefix.get(Prefix, [{"Contents": [], "KeyCount": 0}])


class FakeS3Client:
    def __init__(self, heartbeats: Dict[str, Dict[str, Any]]) -> None:
        from cocli.core.paths import paths

        self._heartbeats = heartbeats
        status_prefix = paths.s3.status_root
        self._paginator = FakePaginator(
            {
                status_prefix: [
                    {
                        "Contents": [
                            {"Key": f"{status_prefix}{host}.json"} for host in heartbeats
                        ]
                    }
                ]
            }
        )

    def get_paginator(self, name: str) -> FakePaginator:
        return self._paginator

    def get_object(self, Bucket: str, Key: str) -> Dict[str, Any]:
        host = Key.split("/")[-1].removesuffix(".json")
        body = json.dumps(self._heartbeats[host]).encode()

        class _Body:
            def read(self_inner) -> bytes:
                return body

        return {"Body": _Body()}


def test_audit_cluster_from_heartbeats_renders_designation_and_health(capsys: Any) -> None:
    from datetime import datetime, timezone

    now_iso = datetime.now(timezone.utc).isoformat()
    heartbeats = {
        "cocli5x0": {
            "timestamp": now_iso,
            "designation": {"gm-list": 2, "gm-details": 2},
            "last_activity": {"gm-list": now_iso, "gm-details": now_iso},
            "error_count_30m": 0,
        },
        "fargate": {
            "timestamp": now_iso,
            "designation": {"enrichment": 2},
            "last_activity": {"enrichment": now_iso},
            "error_count_30m": 1,
        },
    }
    fake_client = FakeS3Client(heartbeats)

    # Wide + no_color: avoids Rich wrapping the Designation column (which
    # would interleave sibling columns' text between "enrichment:" and "2"
    # in the captured output) and avoids ANSI codes splitting substrings -
    # both are rendering details, not what this test is checking.
    with patch.object(audit_module, "console", Console(width=200, no_color=True)), \
        patch("cocli.core.config.load_campaign_config", return_value={}), patch(
        "cocli.core.reporting.get_data_bucket_name", return_value="test-bucket"
    ), patch("cocli.core.reporting.get_boto3_session", return_value=None), patch(
        "cocli.core.reporting.get_s3_client", return_value=fake_client
    ):
        _audit_cluster_from_heartbeats("turboship", verbose=False)

    out = capsys.readouterr().out
    assert "cocli5x0" in out
    assert "fargate" in out
    assert "gm-list: 2" in out
    assert "enrichment: 2" in out


def test_audit_cluster_from_heartbeats_renders_cpu_and_mem(capsys: Any) -> None:
    """CPU/MEM come straight from the same heartbeat JSON already used for
    designation/errors (_push_supervisor_heartbeat's stats["system"]) - this
    pins that the audit table actually surfaces it, not just reads it."""
    from datetime import datetime, timezone

    now_iso = datetime.now(timezone.utc).isoformat()
    heartbeats = {
        "cocli5x0": {
            "timestamp": now_iso,
            "system": {"cpu": 91.4, "mem": 42.0},
            "designation": {"enrichment": 2},
            "last_activity": {"enrichment": now_iso},
            "error_count_30m": 0,
        },
        "cocli5x1": {
            "timestamp": now_iso,
            # No "system" key at all - an older heartbeat writer, or a
            # transient psutil failure - must render "-", not crash.
            "designation": {"enrichment": 3},
            "last_activity": {"enrichment": now_iso},
            "error_count_30m": 0,
        },
    }
    fake_client = FakeS3Client(heartbeats)

    with patch.object(audit_module, "console", Console(width=200, no_color=True)), \
        patch("cocli.core.config.load_campaign_config", return_value={}), patch(
        "cocli.core.reporting.get_data_bucket_name", return_value="test-bucket"
    ), patch("cocli.core.reporting.get_boto3_session", return_value=None), patch(
        "cocli.core.reporting.get_s3_client", return_value=fake_client
    ):
        _audit_cluster_from_heartbeats("turboship", verbose=False)

    out = capsys.readouterr().out
    assert "91" in out
    assert "42" in out
    # cocli5x1 has no "system" key - must degrade to "-", not throw.
    matching_lines = [line for line in out.splitlines() if "cocli5x1" in line]
    assert matching_lines and "-" in matching_lines[0]


def test_audit_cluster_from_heartbeats_tolerates_legacy_naive_timestamp(capsys: Any) -> None:
    # A legacy/non-orchestrator heartbeat writer (e.g. an older standalone
    # node) can emit a naive local timestamp with no tzinfo at all, and a
    # different payload shape entirely - this must not crash the whole
    # command, just render that node with whatever it can make sense of.
    heartbeats = {
        "coclipi": {
            "timestamp": "2026-01-14T15:11:14.356707",
            "campaign": "turboship",
            "system": {"cpu_percent": 5.5, "memory_percent": 58.4},
            "workers": {"scrape": 0, "details": 0, "enrichment": 0},
            "status": "healthy",
        },
    }
    fake_client = FakeS3Client(heartbeats)

    with patch("cocli.core.config.load_campaign_config", return_value={}), patch(
        "cocli.core.reporting.get_data_bucket_name", return_value="test-bucket"
    ), patch("cocli.core.reporting.get_boto3_session", return_value=None), patch(
        "cocli.core.reporting.get_s3_client", return_value=fake_client
    ):
        _audit_cluster_from_heartbeats("turboship", verbose=False)

    out = capsys.readouterr().out
    assert "coclipi" in out


def test_audit_cluster_from_heartbeats_tolerates_epoch_float_timestamp(capsys: Any) -> None:
    # Another real legacy shape found in production S3 data: no designation,
    # no ISO timestamp at all - just a raw epoch float. Must render, not crash.
    heartbeats = {
        "octoprint": {"ip": "172.17.0.2", "timestamp": 1782328414.5509346},
    }
    fake_client = FakeS3Client(heartbeats)

    with patch("cocli.core.config.load_campaign_config", return_value={}), patch(
        "cocli.core.reporting.get_data_bucket_name", return_value="test-bucket"
    ), patch("cocli.core.reporting.get_boto3_session", return_value=None), patch(
        "cocli.core.reporting.get_s3_client", return_value=fake_client
    ):
        _audit_cluster_from_heartbeats("turboship", verbose=False)

    out = capsys.readouterr().out
    assert "octoprint" in out
