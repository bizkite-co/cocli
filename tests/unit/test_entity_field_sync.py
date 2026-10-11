"""Compaction reports the files it rewrote, and the uploader sees only those."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cocli.application.entity_field_sync import compact_and_upload_entity_fields
from cocli.core.paths import paths
from cocli.core.wal import append_update


def test_upload_receives_only_the_rewritten_entity(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(paths, "root", tmp_path)
    company_dir = tmp_path / "companies" / "acme"
    company_dir.mkdir(parents=True)
    (company_dir / "_index.md").write_text("---\nname: Acme\n---\n", encoding="utf-8")
    untouched = tmp_path / "companies" / "other"
    untouched.mkdir(parents=True)
    (untouched / "_index.md").write_text("---\nname: Other\n---\n", encoding="utf-8")
    append_update(company_dir, "city", "Austin", campaign_name="test")

    seen: list[tuple[Path, str]] = []

    def upload(path: Path, key: str) -> None:
        seen.append((path, key))

    did, n_rec, n_ent, keys = compact_and_upload_entity_fields(
        upload,
        data_root=tmp_path,
        wal_root=tmp_path / "wal",
        compactor_id="upload",
    )
    assert did is True
    assert n_rec == 1
    assert n_ent == 1
    assert keys == ["companies/acme/_index.md"]
    assert seen == [(company_dir / "_index.md", "companies/acme/_index.md")]


def test_no_uploader_still_rewrites_the_file(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(paths, "root", tmp_path)
    person_dir = tmp_path / "people" / "mitch-gaylord"
    person_dir.mkdir(parents=True)
    person_file = person_dir / "mitch-gaylord.md"
    person_file.write_text("---\ncity: Dallas\n---\n\n# Mitch\n", encoding="utf-8")
    append_update(person_dir, "city", "Austin", campaign_name="test")

    did, _n_rec, n_ent, keys = compact_and_upload_entity_fields(
        None,
        data_root=tmp_path,
        wal_root=tmp_path / "wal",
    )
    assert did is True
    assert n_ent == 1
    assert keys == []
    assert "Austin" in person_file.read_text(encoding="utf-8")
    assert "# Mitch" in person_file.read_text(encoding="utf-8")
