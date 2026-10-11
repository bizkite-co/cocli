"""A person's campaign relevance follows the linked company's tags."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from cocli.core.cache import build_cache
from cocli.core.paths import paths
from cocli.models.companies.company import Company
from cocli.models.company_name import CompanyName
from cocli.models.people.person import Person


def test_person_inherits_campaign_tag_from_contact_symlink(tmp_path: Path) -> None:
    with patch.object(paths, "root", tmp_path):
        company = Company(
            name=CompanyName("Higginbotham"),
            slug="higginbotham",
            tags=["roadmap"],
        )
        company.save(rebuild_cache=False)
        person = Person(name=CompanyName("Mitch Gaylord"), slug="mitch-gaylord")
        person.save()
        person_file = person.get_file_path()
        assert person_file is not None
        before = person_file.read_bytes()

        contacts = paths.companies.path / "higginbotham" / "contacts"
        contacts.mkdir()
        link = contacts / "mitch-gaylord"
        link.symlink_to(Path("..") / ".." / ".." / "people" / "mitch-gaylord")

        build_cache(campaign="roadmap")

        cache_file = (
            paths.root
            / "campaigns"
            / "roadmap"
            / "indexes"
            / "company_cache"
            / "company_cache.usv"
        )
        content = cache_file.read_text(encoding="utf-8")
        assert person_file.read_bytes() == before

    assert "PERSON:Mitch Gaylord" in content
    assert "mitch-gaylord" in content
    assert "roadmap" in content
