"""Entity field journal: stations LogEdge + per-field LWW (decision 0009)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from stations.protocols import LogEdge

from cocli.core.entity_field_log import (
    apply_field_updates_to_mapping,
    compact_entity_field_journal,
    fold_field_updates,
    open_entity_field_log,
)
from cocli.core.paths import paths
from cocli.core.stations_adapt import accept_log_edge
from cocli.core.wal import append_update, read_updates
from cocli.models.wal.record import DatagramRecord


def test_entity_field_log_edge_is_log_edge() -> None:
    edge = open_entity_field_log(wal_root=Path("/tmp/unused-for-type-gate"))
    typed: LogEdge[DatagramRecord] = accept_log_edge(edge)
    assert typed is edge


def test_phone_and_address_both_survive_fold() -> None:
    """Two writers, two fields: fold keeps both (not whole-record stomp)."""
    recs = [
        DatagramRecord(
            timestamp="2026-07-23T10:00:00+00:00",
            node_id="worker-a",
            campaign_name="test",
            target="companies/acme",
            field="phone",
            value="555-0100",
        ),
        DatagramRecord(
            timestamp="2026-07-23T10:00:01+00:00",
            node_id="worker-b",
            campaign_name="test",
            target="companies/acme",
            field="address",
            value="1 Main St",
        ),
        # later phone overwrites only phone
        DatagramRecord(
            timestamp="2026-07-23T11:00:00+00:00",
            node_id="worker-a",
            campaign_name="test",
            target="companies/acme",
            field="phone",
            value="555-0199",
        ),
    ]
    winners = fold_field_updates(recs)
    by_field = {r.field: r.value for r in winners}
    assert by_field["phone"] == "555-0199"
    assert by_field["address"] == "1 Main St"
    assert len(winners) == 2


def test_apply_field_updates_to_mapping_merges_base() -> None:
    base = {"name": "Acme", "phone": "old"}
    recs = [
        DatagramRecord(
            timestamp="2026-07-23T10:00:00+00:00",
            node_id="n",
            campaign_name="t",
            target="companies/acme",
            field="phone",
            value="555-0100",
        ),
        DatagramRecord(
            timestamp="2026-07-23T10:00:01+00:00",
            node_id="n",
            campaign_name="t",
            target="companies/acme",
            field="address",
            value="1 Main St",
        ),
    ]
    out = apply_field_updates_to_mapping(base, recs)
    assert out["name"] == "Acme"
    assert out["phone"] == "555-0100"
    assert out["address"] == "1 Main St"


def test_append_read_via_log_edge(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(paths, "root", tmp_path)
    company_dir = tmp_path / "companies" / "acme-inc"
    company_dir.mkdir(parents=True)

    append_update(company_dir, "phone", "555-0100", campaign_name="test")
    append_update(company_dir, "address", "1 Main St", campaign_name="test")

    wal_files = list((tmp_path / "wal").glob("*.usv"))
    assert len(wal_files) == 1

    records = read_updates(company_dir)
    fields = {r.field: r.value for r in records}
    assert fields["phone"] == "555-0100"
    assert fields["address"] == "1 Main St"


def test_compact_applies_whole_entity_and_retires_journal(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(paths, "root", tmp_path)
    company_dir = tmp_path / "companies" / "acme-inc"
    company_dir.mkdir(parents=True)
    index = company_dir / "_index.md"
    index.write_text(
        "---\nname: Acme\nphone: old\n---\n\nBody\n",
        encoding="utf-8",
    )

    append_update(company_dir, "phone", "555-0100", campaign_name="test")
    append_update(company_dir, "address", "1 Main St", campaign_name="test")

    did, n_rec, n_ent = compact_entity_field_journal(
        wal_root=tmp_path / "wal",
        data_root=tmp_path,
        apply_to_entities=True,
        compactor_id="test-run",
    )
    assert did is True
    assert n_rec == 2
    assert n_ent == 1

    # Journal segments retired under wal/compacted/
    live = list((tmp_path / "wal").glob("*.usv"))
    assert live == []
    archived = list((tmp_path / "wal" / "compacted" / "test-run").glob("*.usv"))
    assert len(archived) == 1

    text = index.read_text(encoding="utf-8")
    assert "555-0100" in text
    assert "1 Main St" in text
    assert "name: Acme" in text
