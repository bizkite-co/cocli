"""build_cache(): Person records were never indexed (Mark, 2026-10-10).

Two bugs found while diagnosing the TUI People screen's search box
returning nothing despite 1600+ real Person records on disk:

1. The people-scan branch required a flat `<slug>.md` file directly
   under people/, but Person.save() always writes `people/<slug>/<any>.md`
   (one directory per person, like companies) - so `entry.is_file()` was
   never true and zero people were ever added to the cache.
2. `average_rating`/`reviews_count` regex-extraction returned the literal
   string "null" (from a YAML `average_rating: null` scalar) unchanged,
   and `float("null")`/`int("null")` raised inside the company-scan loop -
   silently swallowed by the bg_rebuild() bare try/except in
   search_service.py, so the cache never finished rebuilding at all once
   any company picked up that value.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from cocli.core.cache import build_cache
from cocli.core.paths import paths
from cocli.models.companies.company import Company
from cocli.models.company_name import CompanyName
from cocli.models.people.person import Person


def test_build_cache_indexes_people_stored_in_their_own_directory(
    tmp_path: Path,
) -> None:
    with patch.object(paths, "root", tmp_path):
        person = Person(name="Mitch Gaylord", slug="mitch-gaylord")
        person.save()

        build_cache()

        cache_file = paths.companies.path.parent / "indexes" / "company_cache" / "company_cache.usv"
        content = cache_file.read_text()

    assert "PERSON:Mitch Gaylord" in content
    assert "mitch-gaylord" in content


def test_build_cache_tolerates_a_literal_null_average_rating(tmp_path: Path) -> None:
    with patch.object(paths, "root", tmp_path):
        company = Company(name=CompanyName("Acme"), slug="acme")
        company.save(rebuild_cache=False)
        index_path = paths.companies.path / "acme" / "_index.md"
        text = index_path.read_text()
        text = text.replace(
            "---\n", "---\naverage_rating: null\nreviews_count: null\n", 1
        )
        index_path.write_text(text)

        build_cache()
