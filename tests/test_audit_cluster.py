from cocli.commands.audit import (
    _parse_cluster_audit_sections,
    _node_health_verdict,
    _log_line_age_seconds,
    _format_age,
)


def test_parse_cluster_audit_sections_splits_on_markers():
    raw = (
        "CAMPAIGN_NAME=turboship\n"
        "@@WORKERS@@\n"
        "[2026-06-27 19:28:15 -0700] Starting worker: cocli5x1-gm-details (type=gm-details, workers=2)\n"
        "@@ERRORS@@\n"
        "0\n"
        "@@LASTLOG@@\n"
        "[2026-07-01 00:42:58 -0700] Polling gm-details for tasks...\n"
        "@@TYPE_ACTIVITY@@\n"
        "gm-list|||\n"
        "gm-details|||[2026-07-01 00:42:58 -0700] Polling gm-details for tasks...\n"
        "enrichment|||\n"
        "@@QUEUES@@\n"
        "gm-details/pending=0\n"
        "enrichment/pending=4388\n"
    )
    sections = _parse_cluster_audit_sections(raw)
    assert sections["HEADER"] == ["CAMPAIGN_NAME=turboship"]
    assert len(sections["WORKERS"]) == 1
    assert sections["ERRORS"] == ["0"]
    assert sections["QUEUES"] == ["gm-details/pending=0", "enrichment/pending=4388"]


def test_parse_cluster_audit_sections_handles_missing_container():
    # e.g. SSH succeeds but docker inspect/logs all fail silently
    raw = "@@WORKERS@@\n@@ERRORS@@\n0\n@@LASTLOG@@\n@@TYPE_ACTIVITY@@\ngm-list|||\ngm-details|||\nenrichment|||\n@@QUEUES@@\n"
    sections = _parse_cluster_audit_sections(raw)
    assert sections["HEADER"] == []
    assert sections["LASTLOG"] == []


def test_log_line_age_seconds_parses_bracketed_timestamp():
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    ts = (now - timedelta(seconds=42)).strftime("%Y-%m-%d %H:%M:%S %z")
    age = _log_line_age_seconds(f"[{ts}] Polling gm-details for tasks...")
    assert age is not None
    assert 40 <= age <= 45


def test_log_line_age_seconds_returns_none_for_blank_line():
    assert _log_line_age_seconds("") is None


def test_health_verdict_offline_when_no_campaign():
    assert "OFFLINE" in _node_health_verdict(False, None, 0, [])


def test_health_verdict_stale_when_container_silent():
    assert "STALE" in _node_health_verdict(True, 300.0, 0, [])


def test_health_verdict_flags_stale_content_type_even_if_node_alive():
    # This is the case that motivated per-content-type staleness: the container
    # itself is alive and logging (e.g. gm-details polling every 5s) but a
    # different worker on the same node (enrichment) has silently died.
    verdict = _node_health_verdict(True, 5.0, 0, ["enrichment"])
    assert "STALE" in verdict
    assert "enrichment" in verdict


def test_health_verdict_degraded_on_errors():
    verdict = _node_health_verdict(True, 5.0, 8, [])
    assert "DEGRADED" in verdict


def test_health_verdict_ok_when_healthy():
    verdict = _node_health_verdict(True, 5.0, 0, [])
    assert "OK" in verdict


def test_format_age_seconds_minutes_hours():
    assert _format_age(30) == "30s ago"
    assert _format_age(150) == "2m ago"
    assert _format_age(7200) == "2.0h ago"
