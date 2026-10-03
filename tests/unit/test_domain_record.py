from __future__ import annotations

from typing import Any

from cocli.models.domain_record import DomainRecord


def test_save_creates_a_dot_preserving_folder_not_a_dash_one(tmp_path: Any, monkeypatch: Any) -> None:
    """The actual point (Mark, 2026-10-02): domains/higginbotham.com/,
    not domains/higginbotham-com/ - no dash<->dot translation needed
    anywhere this is used."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    record = DomainRecord(domain="higginbotham.com", employee_directory_url="https://example.com/directory")
    path = record.save()

    assert path == tmp_path / "domains" / "higginbotham.com" / "_index.md"
    assert path.exists()
    assert not (tmp_path / "domains" / "higginbotham-com").exists()


def test_get_round_trips_the_saved_record(tmp_path: Any, monkeypatch: Any) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    DomainRecord(domain="higginbotham.com", employee_directory_url="https://example.com/directory").save()

    loaded = DomainRecord.get("higginbotham.com")
    assert loaded is not None
    assert loaded.employee_directory_url == "https://example.com/directory"


def test_get_returns_none_when_no_record_exists_yet(tmp_path: Any, monkeypatch: Any) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    assert DomainRecord.get("nowhere.example") is None


def test_get_normalizes_www_prefix_to_the_same_record_save_wrote(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """Built from a real bug found while implementing this: save() uses
    the pydantic-validated (www.-stripped) `domain` field, but get()'s
    slug_for() was taking the raw caller-supplied string - so
    get("www.higginbotham.com") looked in a different folder than
    save() actually wrote to. Must resolve to the same record either
    way."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    DomainRecord(domain="higginbotham.com", employee_directory_url="https://example.com/directory").save()

    loaded = DomainRecord.get("www.higginbotham.com")
    assert loaded is not None
    assert loaded.employee_directory_url == "https://example.com/directory"


def test_get_or_create_returns_existing_record_unmodified(tmp_path: Any, monkeypatch: Any) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    DomainRecord(domain="higginbotham.com", employee_directory_url="https://example.com/directory").save()

    record = DomainRecord.get_or_create("higginbotham.com")
    assert record.employee_directory_url == "https://example.com/directory"


def test_get_or_create_returns_a_fresh_unsaved_record_when_none_exists(
    tmp_path: Any, monkeypatch: Any
) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    record = DomainRecord.get_or_create("fresh.example")
    assert record.domain == "fresh.example"
    assert record.employee_directory_url is None
    assert not (tmp_path / "domains" / "fresh.example").exists()


def test_save_is_idempotent_and_updates_in_place_not_appending(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """A second save() must overwrite the same _index.md, not create a
    second entry - this is a single persistent record per domain, same
    convention as a company's own _index.md."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    DomainRecord(domain="higginbotham.com", employee_directory_url="https://old.example/directory").save()
    record = DomainRecord.get_or_create("higginbotham.com")
    record.employee_directory_url = "https://new.example/directory"
    record.save()

    loaded = DomainRecord.get("higginbotham.com")
    assert loaded is not None
    assert loaded.employee_directory_url == "https://new.example/directory"

    domain_dir = tmp_path / "domains" / "higginbotham.com"
    assert sorted(p.name for p in domain_dir.iterdir()) == ["_index.md"]
