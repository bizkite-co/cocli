"""Person model: profile_url field (Mark, 2026-10-09 - a bio/team-page
URL like https://www.higginbotham.com/team/mitchell-gaylord/) and the
get_file_path()/save() contract an editor needs to not duplicate files
on rename."""

from __future__ import annotations

from typing import Any

from cocli.models.people.person import Person


def test_profile_url_round_trips_through_save_and_from_file(
    tmp_path: Any, monkeypatch: Any
) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    person = Person(
        name="Mitch Gaylord",
        slug="mitch-gaylord",
        profile_url="https://www.higginbotham.com/team/mitchell-gaylord/",
    )
    person.save()

    loaded = Person.get("mitch-gaylord")
    assert loaded is not None
    assert loaded.profile_url == "https://www.higginbotham.com/team/mitchell-gaylord/"


def test_get_file_path_returns_the_existing_md_file(tmp_path: Any, monkeypatch: Any) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    person = Person(name="Mitch Gaylord", slug="mitch-gaylord")
    person.save()

    found = person.get_file_path()
    assert found is not None
    assert found.name == "mitch-gaylord.md"


def test_get_file_path_returns_none_before_first_save(tmp_path: Any, monkeypatch: Any) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    person = Person(name="Nobody Yet", slug="nobody-yet")
    assert person.get_file_path() is None


def test_saving_with_person_file_after_a_name_change_does_not_duplicate_the_file(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """The exact bug an editor would hit without get_file_path(): save()
    with no person_file derives a filename from self.name, so renaming
    then re-saving without pinning the original path leaves both the
    old and new .md files on disk."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    person = Person(name="Mitch Gaylord", slug="mitch-gaylord")
    person.save()
    original_file = person.get_file_path()
    assert original_file is not None

    renamed = Person(name="Mitchell Gaylord", slug="mitch-gaylord", profile_url="https://x.test")
    renamed.save(person_file=original_file)

    md_files = list(person.get_local_path().glob("*.md"))
    assert len(md_files) == 1

    loaded = Person.get("mitch-gaylord")
    assert loaded is not None
    assert str(loaded.name) == "Mitchell Gaylord"
    assert loaded.profile_url == "https://x.test"
