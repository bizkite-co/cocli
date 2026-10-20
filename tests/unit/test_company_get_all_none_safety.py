"""Company.get_all() yields None for unparseable directories - regression
coverage for a real crash: render_prospects_kml.py (and 4 other call sites)
called .place_id/.tags/.domain etc. directly on the yielded value without
checking for None first, since get_all()'s declared return type used to lie
(Iterator["Company"], not Iterator[Optional["Company"]]).
"""

from pathlib import Path

from cocli.core.paths import paths
from cocli.core.wal import append_update
from cocli.models.companies.company import Company


def test_get_all_yields_none_for_directory_without_index_md(tmp_path: Path) -> None:
    paths.root = tmp_path

    good = paths.companies.entry("good-co").path
    good.mkdir(parents=True)
    (good / "_index.md").write_text(
        "---\nname: Good Co\nslug: good-co\n---\n", encoding="utf-8"
    )

    malformed = paths.companies.entry("malformed-co").path
    malformed.mkdir(parents=True)
    # No _index.md - Company.from_directory() returns None for this.

    results = list(Company.get_all())
    assert any(c is not None and c.slug == "good-co" for c in results)
    assert any(c is None for c in results)


def test_cleared_callback_at_still_loads_the_company(tmp_path: Path) -> None:
    """A follow-up cleared in the Call Log journals callback_at as \"\".

    That blank must not hide the company from the TUI.
    """
    paths.root = tmp_path
    company_dir = paths.companies.entry("higginbotham-richard-bendes").path
    company_dir.mkdir(parents=True)
    (company_dir / "_index.md").write_text(
        "---\n"
        "name: Higginbotham - Richard Bendes\n"
        "slug: higginbotham-richard-bendes\n"
        "phone_number: '15124574000'\n"
        "---\n",
        encoding="utf-8",
    )
    append_update(company_dir, "callback_at", "", campaign_name="roadmap")

    loaded = Company.from_directory(company_dir)

    assert loaded is not None
    assert loaded.callback_at is None
    assert str(loaded.phone_number) == "15124574000"


def test_render_prospects_kml_company_lookup_skips_none_entries(tmp_path: Path) -> None:
    """Reproduces the exact loop shape from render_prospects_kml.py's
    Company lookup-table build - must not raise on the malformed directory."""
    paths.root = tmp_path

    good = paths.companies.entry("good-co").path
    good.mkdir(parents=True)
    (good / "_index.md").write_text(
        "---\nname: Good Co\nslug: good-co\n---\n", encoding="utf-8"
    )

    malformed = paths.companies.entry("malformed-co").path
    malformed.mkdir(parents=True)

    companies_by_place_id = {}
    companies_by_slug = {}
    companies_by_hash = {}
    for company_obj in Company.get_all():
        if company_obj is None:
            continue
        if company_obj.place_id:
            companies_by_place_id[company_obj.place_id] = company_obj
        companies_by_slug[company_obj.slug] = company_obj
        if company_obj.company_hash:
            companies_by_hash[company_obj.company_hash] = company_obj

    assert companies_by_slug["good-co"].slug == "good-co"
