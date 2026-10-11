"""Relationship journal: stations LogEdge + ADR-014 folds."""

from __future__ import annotations

from pathlib import Path

from stations.protocols import LogEdge

from cocli.application.relationships import FoldPolicy, fold_policy
from cocli.core.relationship_log import (
    fold_observation_members,
    fold_observations,
    fold_relationship_instances,
    open_relationship_log,
)
from cocli.core.stations_adapt import accept_log_edge
from cocli.models.wal.relationship import RelationshipRecord


def _rec(
    *,
    relationship_id: str = "edge-1",
    timestamp: str = "2026-10-11T00:00:00+00:00",
    node_id: str = "dev",
    campaign_name: str = "roadmap",
    subject_type: str = "person",
    subject: str = "mitch-gaylord",
    predicate: str = "worksFor",
    object_type: str = "company",
    object_key: str = "higginbotham",
    started_at: str = "2024-01-01",
    ended_at: str = "",
    is_primary: bool = False,
    source: str = "manual",
    method: str = "osint",
    observed_at: str = "2026-10-11",
) -> RelationshipRecord:
    return RelationshipRecord(
        relationship_id=relationship_id,
        timestamp=timestamp,
        node_id=node_id,
        campaign_name=campaign_name,
        subject_type=subject_type,
        subject=subject,
        predicate=predicate,
        object_type=object_type,
        object_key=object_key,
        started_at=started_at,
        ended_at=ended_at,
        is_primary=is_primary,
        source=source,
        method=method,
        observed_at=observed_at,
    )


def test_usv_roundtrip_uses_newline_not_record_separator() -> None:
    raw = _rec(is_primary=True).to_usv()
    assert raw.endswith("\n")
    assert "\x1e" not in raw
    assert "\x1f" in raw
    parsed = RelationshipRecord.from_usv(raw)
    assert parsed.relationship_id == "edge-1"
    assert parsed.is_primary is True
    assert parsed.object_key == "higginbotham"
    assert parsed.ended_at == ""


def test_relationship_log_edge_is_log_edge() -> None:
    edge = open_relationship_log(wal_root=Path("/tmp/unused-relationship-log"))
    typed: LogEdge[RelationshipRecord] = accept_log_edge(edge)
    assert typed is edge
    assert edge.station.name == "relationship-journal"


def test_append_and_iter(tmp_path: Path) -> None:
    edge = open_relationship_log(wal_root=tmp_path)
    edge.append(_rec())
    edge.append(
        _rec(
            relationship_id="edge-2",
            subject="other",
            predicate="membership",
        )
    )
    rows = list(edge.iter_beyond())
    assert {row.relationship_id for row in rows} == {"edge-1", "edge-2"}
    segments = list(tmp_path.glob("*.usv"))
    assert len(segments) == 1
    assert segments[0].name.endswith("_dev.usv")


def test_two_stints_survive_instance_fold() -> None:
    """Same person and company, two ids: both intervals remain."""
    first = _rec(
        relationship_id="stint-1",
        timestamp="2022-01-01T00:00:00+00:00",
        started_at="2020-01-01",
        ended_at="2022-06-01",
    )
    close = _rec(
        relationship_id="stint-1",
        timestamp="2022-06-02T00:00:00+00:00",
        started_at="2020-01-01",
        ended_at="2022-06-01",
    )
    second = _rec(
        relationship_id="stint-2",
        timestamp="2025-01-01T00:00:00+00:00",
        started_at="2025-01-01",
    )
    winners = fold_relationship_instances([first, close, second])
    by_id = {row.relationship_id: row for row in winners}
    assert set(by_id) == {"stint-1", "stint-2"}
    assert by_id["stint-1"].ended_at == "2022-06-01"
    assert by_id["stint-1"].timestamp == "2022-06-02T00:00:00+00:00"
    assert by_id["stint-2"].ended_at == ""


def test_member_fold_keeps_each_product() -> None:
    salesforce_old = _rec(
        relationship_id="tech-1",
        timestamp="2026-01-01T00:00:00+00:00",
        subject_type="company",
        subject="higginbotham",
        predicate="usesTechnology",
        object_type="literal",
        object_key="salesforce",
        source="website",
    )
    salesforce_new = _rec(
        relationship_id="tech-2",
        timestamp="2026-06-01T00:00:00+00:00",
        subject_type="company",
        subject="higginbotham",
        predicate="usesTechnology",
        object_type="literal",
        object_key="salesforce",
        source="website",
    )
    mimecast = _rec(
        relationship_id="tech-3",
        timestamp="2026-06-01T00:00:00+00:00",
        subject_type="company",
        subject="higginbotham",
        predicate="usesTechnology",
        object_type="literal",
        object_key="mimecast",
        source="dig MX",
    )
    winners = fold_observation_members([salesforce_old, salesforce_new, mimecast])
    by_product = {row.object_key: row.timestamp for row in winners}
    assert by_product == {
        "salesforce": "2026-06-01T00:00:00+00:00",
        "mimecast": "2026-06-01T00:00:00+00:00",
    }


def test_observation_fold_keeps_latest_per_predicate() -> None:
    older = _rec(
        relationship_id="obs-1",
        timestamp="2026-01-01T00:00:00+00:00",
        subject_type="company",
        subject="higginbotham",
        predicate="usesEmailService",
        object_type="literal",
        object_key="google-workspace",
        source="dig MX",
    )
    newer = _rec(
        relationship_id="obs-2",
        timestamp="2026-06-01T00:00:00+00:00",
        subject_type="company",
        subject="higginbotham",
        predicate="usesEmailService",
        object_type="literal",
        object_key="mimecast",
        source="dig MX",
    )
    other = _rec(
        relationship_id="obs-3",
        timestamp="2026-06-01T00:00:00+00:00",
        subject_type="company",
        subject="higginbotham",
        predicate="usesTechnology",
        object_type="literal",
        object_key="salesforce",
    )
    winners = fold_observations([older, newer, other])
    by_pred = {row.predicate: row.object_key for row in winners}
    assert by_pred == {
        "usesEmailService": "mimecast",
        "usesTechnology": "salesforce",
    }


def test_predicate_registry_assigns_folds() -> None:
    assert fold_policy("parentOrganization") is FoldPolicy.INSTANCE
    assert fold_policy("worksFor") is FoldPolicy.INSTANCE
    assert fold_policy("usesEmailService") is FoldPolicy.OBSERVATION
    assert fold_policy("usesTechnology") is FoldPolicy.OBSERVATION_MEMBER
    try:
        fold_policy("branch_of")
    except ValueError as exc:
        assert "branch_of" in str(exc)
    else:
        raise AssertionError("unknown predicate must raise")
