"""Person.save journals changed fields, and load overlays them."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cocli.core.paths import paths
from cocli.core.wal import append_update, read_updates
from cocli.models.company_name import CompanyName
from cocli.models.people.person import Person


def test_save_appends_a_changed_field_and_writes_the_file(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(paths, "root", tmp_path)
    person = Person(
        name=CompanyName("Mitch Gaylord"),
        slug="mitch-gaylord",
        profile_url="https://old.example/",
    )
    person.save()
    person_dir = paths.people.path / "mitch-gaylord"
    assert read_updates(person_dir) == []

    person.profile_url = "https://www.higginbotham.com/team/mitchell-gaylord/"
    person.save(person_file=person.get_file_path())

    records = read_updates(person_dir)
    text = (person_dir / "mitch-gaylord.md").read_text(encoding="utf-8")
    assert [record.field for record in records] == ["profile_url"]
    assert records[0].value == "https://www.higginbotham.com/team/mitchell-gaylord/"
    assert records[0].target == "people/mitch-gaylord"
    assert "mitchell-gaylord" in text


def test_second_save_with_no_change_appends_nothing(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(paths, "root", tmp_path)
    person = Person(name=CompanyName("Mitch Gaylord"), slug="mitch-gaylord", city="Dallas")
    person.save()
    person.city = "Austin"
    person.save(person_file=person.get_file_path())
    person.save(person_file=person.get_file_path())
    records = read_updates(paths.people.path / "mitch-gaylord")
    assert len(records) == 1


def test_use_wal_false_writes_the_file_and_appends_nothing(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(paths, "root", tmp_path)
    person = Person(name=CompanyName("Mitch Gaylord"), slug="mitch-gaylord", city="Dallas")
    person.save(use_wal=False)
    person.city = "Austin"
    person.save(person_file=person.get_file_path(), use_wal=False)
    records = read_updates(paths.people.path / "mitch-gaylord")
    text = (paths.people.path / "mitch-gaylord" / "mitch-gaylord.md").read_text(
        encoding="utf-8"
    )
    assert records == []
    assert "Austin" in text


def test_from_file_overlays_a_journaled_profile_url(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(paths, "root", tmp_path)
    person = Person(
        name=CompanyName("Mitch Gaylord"),
        slug="mitch-gaylord",
        profile_url="https://old.example/",
    )
    person.save(use_wal=False)
    person_dir = paths.people.path / "mitch-gaylord"
    append_update(
        person_dir,
        "profile_url",
        "https://www.higginbotham.com/team/mitchell-gaylord/",
        campaign_name="test",
    )

    loaded = Person.get("mitch-gaylord")
    assert loaded is not None
    assert loaded.profile_url == "https://www.higginbotham.com/team/mitchell-gaylord/"
    stored = (person_dir / "mitch-gaylord.md").read_text(encoding="utf-8")
    assert "https://old.example/" in stored
