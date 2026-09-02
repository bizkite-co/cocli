import json
from typing import Any
from unittest.mock import patch

from rich.console import Console
from typer.testing import CliRunner

import cocli.commands.audit as audit_module
from cocli.commands.audit import (
    _audit_cluster_from_heartbeats,
    _classify_error_message,
    _count_error_types,
    _parse_cluster_audit_sections,
)


class FakePaginator:
    def __init__(self, pages_by_prefix: dict[str, list[dict[str, Any]]]) -> None:
        self._pages_by_prefix = pages_by_prefix

    def paginate(self, Bucket: str, Prefix: str) -> list[dict[str, Any]]:
        return self._pages_by_prefix.get(Prefix, [{"Contents": [], "KeyCount": 0}])


class FakeS3Client:
    def __init__(
        self,
        heartbeats: dict[str, dict[str, Any]],
        queue_keys_by_prefix: dict[str, list[str]] | None = None,
    ) -> None:
        from cocli.core.paths import paths

        self._heartbeats = heartbeats
        status_prefix = paths.s3.status_root
        pages: dict[str, list[dict[str, Any]]] = {
            status_prefix: [
                {
                    "Contents": [
                        {"Key": f"{status_prefix}{host}.json"} for host in heartbeats
                    ]
                }
            ]
        }
        for prefix, keys in (queue_keys_by_prefix or {}).items():
            pages[prefix] = [{"Contents": [{"Key": k} for k in keys]}]
        self._paginator = FakePaginator(pages)

    def get_paginator(self, name: str) -> FakePaginator:
        return self._paginator

    def get_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        host = Key.split("/")[-1].removesuffix(".json")
        body = json.dumps(self._heartbeats[host]).encode()

        class _Body:
            def read(self_inner) -> bytes:
                return body

        return {"Body": _Body()}


def test_classify_error_message_extracts_exception_class() -> None:
    assert _classify_error_message(
        "Future exception was never retrieved: TargetClosedError('Target page, "
        "context or browser has been closed')"
    ) == "TargetClosedError"
    assert _classify_error_message(
        "Task Failed: No item yielded within 90s (idle timeout)"
    ) == "Task Failed"


def test_count_error_types_sorts_by_frequency_descending() -> None:
    messages = [
        "Future exception was never retrieved: TargetClosedError(...)",
        "Task Failed: No item yielded within 90s (idle timeout)",
        "Future exception was never retrieved: TargetClosedError(...)",
        "Future exception was never retrieved: TargetClosedError(...)",
    ]
    counts = _count_error_types(messages)
    assert counts[0] == ("TargetClosedError", 3)
    assert counts[1] == ("Task Failed", 1)


def test_audit_cluster_from_heartbeats_verbose_prints_error_type_counts(
    capsys: Any,
) -> None:
    """Verbose mode should surface a "list of error types and counts" the
    user can scan at a glance, not just N raw message lines to eyeball for
    repeats."""
    from datetime import datetime, timezone

    now_iso = datetime.now(timezone.utc).isoformat()
    heartbeats = {
        "cocli5x0": {
            "timestamp": now_iso,
            "designation": {"gm-list": 1},
            "last_activity": {"gm-list": now_iso},
            "error_count_30m": 3,
            "recent_errors": [
                "Future exception was never retrieved: TargetClosedError(...)",
                "Future exception was never retrieved: TargetClosedError(...)",
                "Task Failed: No item yielded within 90s (idle timeout)",
            ],
        },
    }
    fake_client = FakeS3Client(heartbeats)

    with patch.object(audit_module, "console", Console(width=200, no_color=True)), \
        patch("cocli.core.config.load_campaign_config", return_value={}), patch(
        "cocli.core.reporting.get_data_bucket_name", return_value="test-bucket"
    ), patch("cocli.core.reporting.get_boto3_session", return_value=None), patch(
        "cocli.core.reporting.get_s3_client", return_value=fake_client
    ):
        _audit_cluster_from_heartbeats("turboship", verbose=True)

    out = capsys.readouterr().out
    assert "error types (last 3 messages)" in out
    assert "TargetClosedError" in out
    assert "  2  TargetClosedError" in out


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


def test_audit_cluster_from_heartbeats_flags_campaign_mismatch(capsys: Any) -> None:
    """The heartbeat's own "campaign" field (added 2026-08-07) is the node's
    live self-report of what it's actually running - a confirmed drift
    incident showed a node's config.toml can say one thing while the
    running container serves another. A node whose heartbeat campaign
    doesn't match the campaign we queried must be visibly flagged, not
    silently displayed as if everything's normal."""
    from datetime import datetime, timezone

    now_iso = datetime.now(timezone.utc).isoformat()
    heartbeats = {
        "cocli5x0": {
            "timestamp": now_iso,
            "campaign": "turboship",
            "designation": {"gm-list": 2},
            "last_activity": {"gm-list": now_iso},
            "error_count_30m": 0,
        },
        "cocli5x1": {
            "timestamp": now_iso,
            "campaign": "roadmap",
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
    lines = out.splitlines()
    cocli5x0_line = next(line for line in lines if "cocli5x0" in line)
    cocli5x1_line = next(line for line in lines if "cocli5x1" in line)
    assert "turboship" in cocli5x0_line
    assert "!=" not in cocli5x0_line  # matches the queried campaign - no flag
    assert "roadmap" in cocli5x1_line
    assert "!= turboship" in cocli5x1_line  # live campaign disagrees - flagged


def test_queue_depths_exclude_lease_attempts_and_sidecar_files(capsys: Any) -> None:
    """The real bug this pins: raw S3 KeyCount under a queue prefix counted
    every lease*.json (claimed task), attempts*.json (retried task), and
    datapackage.json/mission.usv sidecar as if it were its own pending
    task - silently inflating "Pending" well past the true number of
    distinct tasks still waiting.

    Uses gm-details, not gm-list: gm-list's real work pool is
    discovery-gen/completed (a witness-indexed pool), not queues/gm-list/
    pending/, so that specific queue's pending count is intentionally
    skipped entirely now (see test_gm_list_pending_omitted_not_zeroed) -
    the lease/attempts/sidecar filtering this test pins still applies to
    every other queue type that does count its pending/ prefix for real."""
    from datetime import datetime, timezone

    now_iso = datetime.now(timezone.utc).isoformat()
    heartbeats = {
        "cocli5x0": {
            "timestamp": now_iso,
            "designation": {"gm-details": 1},
            "last_activity": {"gm-details": now_iso},
            "error_count_30m": 0,
        },
    }
    gm_details_pending_prefix = "campaigns/turboship/queues/gm-details/pending/"
    fake_client = FakeS3Client(
        heartbeats,
        queue_keys_by_prefix={
            gm_details_pending_prefix: [
                # 2 real pending tasks...
                f"{gm_details_pending_prefix}2/28.0/-82.7/commercial-vinyl-flooring-contractor.usv",
                f"{gm_details_pending_prefix}2/28.3/-81.5/rubber-flooring-contractor.usv",
                # ...but one of them is claimed (adds a lease file)...
                f"{gm_details_pending_prefix}2/28.0/-82.7/commercial-vinyl-flooring-contractor/lease.json",
                # ...one has been retried (adds an attempts file)...
                f"{gm_details_pending_prefix}2/28.3/-81.5/rubber-flooring-contractor/attempts.json",
                # ...and the queue-wide sidecars are always present regardless
                # of how many real tasks exist.
                f"{gm_details_pending_prefix}datapackage.json",
                f"{gm_details_pending_prefix}mission.usv",
            ],
        },
    )

    with patch.object(audit_module, "console", Console(width=200, no_color=True)), \
        patch("cocli.core.config.load_campaign_config", return_value={}), patch(
        "cocli.core.reporting.get_data_bucket_name", return_value="test-bucket"
    ), patch("cocli.core.reporting.get_boto3_session", return_value=None), patch(
        "cocli.core.reporting.get_s3_client", return_value=fake_client
    ):
        _audit_cluster_from_heartbeats("turboship", verbose=False)

    out = capsys.readouterr().out
    # "gm-details: N" (with a colon) is the Cluster Node Audit table's
    # Designation cell - the Campaign Queue Depths table's Queue column is
    # just the bare word "gm-details", so exclude the colon form to isolate it.
    lines = [
        line for line in out.splitlines()
        if "gm-details" in line and "gm-details:" not in line
    ]
    assert lines, "expected a gm-details row in the Campaign Queue Depths table"
    # 6 raw keys were provided; only 2 are real distinct pending tasks.
    assert " 2 " in lines[0], f"expected exactly 2 real pending tasks, got: {lines[0]!r}"


def test_gm_list_pending_omitted_not_zeroed(capsys: Any) -> None:
    """gm-list's real work pool is discovery-gen/completed, not queues/
    gm-list/pending/ (near-permanently empty by design) - counting it would
    render a confident-looking "0" indistinguishable from "genuinely no work
    left", when the truth is just "this counter doesn't know where to look".
    Must render "-", not 0."""
    from datetime import datetime, timezone

    now_iso = datetime.now(timezone.utc).isoformat()
    heartbeats = {
        "cocli5x0": {
            "timestamp": now_iso,
            "designation": {"gm-list": 1},
            "last_activity": {"gm-list": now_iso},
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
    lines = [
        line for line in out.splitlines()
        if "gm-list" in line and "gm-list:" not in line
    ]
    assert lines, "expected a gm-list row in the Campaign Queue Depths table"
    assert "-" in lines[0], f"expected pending rendered as '-', got: {lines[0]!r}"


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


def test_audit_cluster_defaults_to_ssh_not_s3(cli_app) -> None:
    """SSH (concurrent, per-node) is the default path now - S3 heartbeat
    fan-in became the default in July for Fargate coverage, but that made
    every plain `cocli audit cluster` call pay 9+ paginated S3 listings (and
    an 1Password/Windows-Hello prompt) even for campaigns with no Fargate
    node at all. --s3 opts back into the old heartbeat-only path."""
    runner = CliRunner()
    with patch.object(audit_module, "_audit_cluster_ssh") as mock_ssh, \
        patch.object(audit_module, "_audit_cluster_from_heartbeats") as mock_s3:
        result = runner.invoke(cli_app, ["audit", "cluster", "--campaign", "roadmap"])

    assert result.exit_code == 0
    mock_ssh.assert_called_once_with("roadmap", False)
    mock_s3.assert_not_called()


def test_audit_cluster_s3_flag_opts_into_heartbeat_path(cli_app) -> None:
    runner = CliRunner()
    with patch.object(audit_module, "_audit_cluster_ssh") as mock_ssh, \
        patch.object(audit_module, "_audit_cluster_from_heartbeats") as mock_s3:
        result = runner.invoke(cli_app, ["audit", "cluster", "--campaign", "roadmap", "--s3"])

    assert result.exit_code == 0
    mock_s3.assert_called_once_with("roadmap", False)
    mock_ssh.assert_not_called()


def test_parse_cluster_audit_sections_handles_glued_marker() -> None:
    """Regression pin: `docker exec ... cat /tmp/cocli_heartbeat.json` doesn't
    emit a trailing newline (the JSON file has none), so without an explicit
    blank `echo` before the next `echo '@@WORKERS@@'` in the remote script,
    the marker glues onto the JSON's closing brace as `...}@@WORKERS@@` and
    never matches `markers` exactly - silently emptying every section from
    WORKERS onward with no exception, just wrong (blank) data. Caught live
    on cocli5x1, not by any test, before this pin existed."""
    raw = (
        "CAMPAIGN_NAME=roadmap\n"
        "@@HEARTBEAT@@\n"
        '{"campaign": "roadmap", "system": {"cpu": 12.0, "mem": 8.0}}@@WORKERS@@\n'
        "Starting worker: scraper-1 (type=gm-list, workers=2)\n"
        "@@ERRORS@@\n"
        "3\n"
    )
    sections = _parse_cluster_audit_sections(raw)

    # The glued case: only @@WORKERS@@ (immediately after the no-trailing-
    # newline JSON) fails to match - it and everything until the next real
    # marker (@@ERRORS@@, still on its own line) fall into HEARTBEAT instead.
    assert sections["WORKERS"] == []
    assert sections["ERRORS"] == ["3"]
    assert len(sections["HEARTBEAT"]) == 2
    assert "@@WORKERS@@" in sections["HEARTBEAT"][0]


def test_parse_cluster_audit_sections_normal_shape() -> None:
    """Positive case: each marker on its own line (the fixed remote script,
    with the blank `echo` separator) partitions cleanly."""
    raw = (
        "CAMPAIGN_NAME=roadmap\n"
        "@@HEARTBEAT@@\n"
        '{"campaign": "roadmap", "system": {"cpu": 12.0, "mem": 8.0}}\n'
        "\n"
        "@@WORKERS@@\n"
        "Starting worker: scraper-1 (type=gm-list, workers=2)\n"
        "@@ERRORS@@\n"
        "3\n"
    )
    sections = _parse_cluster_audit_sections(raw)

    assert sections["HEARTBEAT"] == ['{"campaign": "roadmap", "system": {"cpu": 12.0, "mem": 8.0}}', ""]
    assert sections["WORKERS"] == ["Starting worker: scraper-1 (type=gm-list, workers=2)"]
    assert sections["ERRORS"] == ["3"]
