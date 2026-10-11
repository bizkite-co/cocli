"""Present-state org.md and symlinks from the relationship journal."""

from __future__ import annotations

from pathlib import Path

from cocli.application.relationship_present import publish_relationship_journal
from cocli.core.relationship_log import open_relationship_log
from cocli.models.wal.relationship import RelationshipRecord


def _rec(
    *,
    relationship_id: str = "edge-1",
    timestamp: str = "2026-10-11T00:00:00+00:00",
    node_id: str = "dev",
    campaign_name: str = "roadmap",
    subject_type: str = "company",
    subject: str = "higginbotham-austin",
    predicate: str = "parentOrganization",
    object_type: str = "company",
    object_key: str = "higginbotham",
    started_at: str = "2019-04-01",
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


def test_publish_writes_org_chart_and_keeps_journal(tmp_path: Path) -> None:
    data = tmp_path / "data"
    (data / "companies" / "higginbotham").mkdir(parents=True)
    (data / "companies" / "higginbotham-austin").mkdir(parents=True)
    (data / "people" / "mitch-gaylord").mkdir(parents=True)
    # A real file in contacts/ must survive symlink regeneration.
    contacts = data / "companies" / "higginbotham" / "contacts"
    contacts.mkdir()
    (contacts / "notes.txt").write_text("keep\n", encoding="utf-8")

    wal = tmp_path / "wal"
    edge = open_relationship_log(wal_root=wal)
    edge.append(
        _rec(
            relationship_id="branch-1",
            subject="higginbotham-austin",
            predicate="parentOrganization",
            object_key="higginbotham",
        )
    )
    edge.append(
        _rec(
            relationship_id="job-1",
            subject_type="person",
            subject="mitch-gaylord",
            predicate="worksFor",
            object_type="company",
            object_key="higginbotham",
            started_at="2024-01-01",
            is_primary=True,
        )
    )

    written = publish_relationship_journal(data_root=data, wal_root=wal)
    assert written == 2
    assert list(wal.glob("*.usv"))

    parent = (data / "companies" / "higginbotham" / "org.md").read_text(encoding="utf-8")
    assert "# higginbotham" in parent
    assert "higginbotham-austin" in parent
    assert "mitch-gaylord" in parent
    assert "primary=yes" in parent

    child = (data / "companies" / "higginbotham-austin" / "org.md").read_text(
        encoding="utf-8"
    )
    assert "parentOrganization:" in child
    assert "- higginbotham since=2019-04-01" in child

    unit = data / "companies" / "higginbotham" / "units" / "higginbotham-austin"
    person = data / "companies" / "higginbotham" / "contacts" / "mitch-gaylord"
    assert unit.is_symlink()
    assert person.is_symlink()
    assert unit.resolve() == (data / "companies" / "higginbotham-austin").resolve()
    assert person.resolve() == (data / "people" / "mitch-gaylord").resolve()
    assert (contacts / "notes.txt").read_text(encoding="utf-8") == "keep\n"


def test_republish_drops_closed_symlink_and_keeps_segments(tmp_path: Path) -> None:
    data = tmp_path / "data"
    (data / "companies" / "higginbotham").mkdir(parents=True)
    (data / "people" / "mitch-gaylord").mkdir(parents=True)
    wal = tmp_path / "wal"
    edge = open_relationship_log(wal_root=wal)
    edge.append(
        _rec(
            relationship_id="job-1",
            timestamp="2024-01-01T00:00:00+00:00",
            subject_type="person",
            subject="mitch-gaylord",
            predicate="worksFor",
            object_key="higginbotham",
            started_at="2024-01-01",
        )
    )
    publish_relationship_journal(data_root=data, wal_root=wal)
    link = data / "companies" / "higginbotham" / "contacts" / "mitch-gaylord"
    assert link.is_symlink()

    edge.append(
        _rec(
            relationship_id="job-1",
            timestamp="2026-01-01T00:00:00+00:00",
            subject_type="person",
            subject="mitch-gaylord",
            predicate="worksFor",
            object_key="higginbotham",
            started_at="2024-01-01",
            ended_at="2025-12-31",
        )
    )
    publish_relationship_journal(data_root=data, wal_root=wal)
    assert not link.exists()
    text = (data / "companies" / "higginbotham" / "org.md").read_text(encoding="utf-8")
    assert "mitch-gaylord" not in text
    assert list(wal.glob("*.usv"))
