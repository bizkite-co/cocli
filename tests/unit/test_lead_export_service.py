"""Unit tests for lead_export_service.export_enriched_emails.

Extracted from scripts/export_enriched_emails.py after a hand-rolled
reimplementation of this exact query (in a different investigation script,
same session) undercounted real results by omitting the found_keywords
join - see docs/data-management/data-quality-incidents/README.md. The
found_keywords test below locks that specific gap in.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from cocli.application.lead_export_service import export_enriched_emails
from cocli.core.paths import paths
from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect

CAMPAIGN = "test-campaign"
US = "\x1f"


def _setup(tmp_path: Path) -> None:
    paths.root = tmp_path
    (tmp_path / "campaigns" / CAMPAIGN / "indexes" / "google_maps_prospects").mkdir(parents=True)
    (tmp_path / "campaigns" / CAMPAIGN / "indexes" / "emails" / "shards").mkdir(parents=True)
    (tmp_path / "campaigns" / CAMPAIGN / "exports").mkdir(parents=True)
    (tmp_path / "campaigns" / CAMPAIGN / "exclusions").mkdir(parents=True)
    (tmp_path / "companies").mkdir(parents=True)


def _write_checkpoint(tmp_path: Path, rows: List[str]) -> None:
    checkpoint = (
        tmp_path / "campaigns" / CAMPAIGN / "indexes" / "google_maps_prospects" / "prospects.usv"
    )
    with open(checkpoint, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(row + "\n")


def _write_email_shard(tmp_path: Path, email: str, domain: str, slug: str) -> None:
    shard = tmp_path / "campaigns" / CAMPAIGN / "indexes" / "emails" / "shards" / "00.usv"
    row = US.join([email, domain, slug, "test", "2026-01-01", "2026-01-01", "2026-01-01", "unknown", ""])
    with open(shard, "a", encoding="utf-8") as f:
        f.write(row + "\n")


def _prospect(
    place_id: str,
    slug: str,
    name: str,
    domain: str,
    phone: str = "5551234567",
    category: Optional[str] = None,
) -> str:
    """Builds a full-width checkpoint row directly (bypasses the Pydantic
    constructor's strict Annotated field typing - matches the pattern in
    test_prospects_stations_compact.py)."""
    names = GoogleMapsProspect.usv_field_names()
    cols = [""] * len(names)
    idx = {n: i for i, n in enumerate(names)}
    cols[idx["place_id"]] = place_id
    cols[idx["slug"]] = slug
    cols[idx["name"]] = name
    cols[idx["domain"]] = domain
    cols[idx["phone"]] = phone
    if category:
        cols[idx["category"]] = category
    return US.join(cols)


def test_join_by_slug_and_default_filters(tmp_path: Path) -> None:
    _setup(tmp_path)
    _write_checkpoint(tmp_path, [
        _prospect("ChIJAAAAAAAAAAAAAAAAAAAAAAA", "acme-corp", "Acme Corp", "acme.com", category="Flooring contractor"),
    ])
    _write_email_shard(tmp_path, "info@acme.com", "acme.com", "acme-corp")

    result = export_enriched_emails(CAMPAIGN)

    assert result.exported_count == 1
    assert result.output_csv is not None
    content = result.output_csv.read_text()
    assert "Acme Corp" in content
    assert "info@acme.com" in content
    assert "Flooring contractor" in content


def test_missing_email_excluded_by_default(tmp_path: Path) -> None:
    _setup(tmp_path)
    _write_checkpoint(tmp_path, [
        _prospect("ChIJBBBBBBBBBBBBBBBBBBBBBBB", "no-email-corp", "No Email Corp", "noemail.com", category="Flooring contractor"),
    ])
    # no matching email shard entry

    result = export_enriched_emails(CAMPAIGN)

    assert result.exported_count == 0


def test_include_all_includes_rows_with_no_email(tmp_path: Path) -> None:
    _setup(tmp_path)
    _write_checkpoint(tmp_path, [
        _prospect("ChIJCCCCCCCCCCCCCCCCCCCCCCC", "no-email-corp", "No Email Corp", "noemail.com", category="Flooring contractor"),
    ])

    result = export_enriched_emails(CAMPAIGN, include_all=True)

    assert result.exported_count == 1
    assert result.output_csv is not None
    content = result.output_csv.read_text()
    assert "No Email Corp" in content


def test_missing_phone_excluded(tmp_path: Path) -> None:
    _setup(tmp_path)
    _write_checkpoint(tmp_path, [
        _prospect("ChIJDDDDDDDDDDDDDDDDDDDDDDD", "no-phone-corp", "No Phone Corp", "nophone.com", phone="", category="Flooring contractor"),
    ])
    _write_email_shard(tmp_path, "info@nophone.com", "nophone.com", "no-phone-corp")

    result = export_enriched_emails(CAMPAIGN, include_all=True)

    assert result.exported_count == 0


def test_found_keywords_alone_satisfies_category_requirement(tmp_path: Path) -> None:
    """The regression this whole module exists to prevent: a company with
    NO checkpoint category/keyword can still qualify purely on the
    company's own website-enrichment found_keywords. A reimplementation
    that only checks the checkpoint's category/first_category columns
    (like the flawed one this session accidentally wrote) silently
    undercounts real results by missing this path entirely."""
    _setup(tmp_path)
    _write_checkpoint(tmp_path, [
        _prospect("ChIJEEEEEEEEEEEEEEEEEEEEEEE", "keyword-corp", "Keyword Corp", "keywordcorp.com", category=None),
    ])
    _write_email_shard(tmp_path, "info@keywordcorp.com", "keywordcorp.com", "keyword-corp")

    company_dir = tmp_path / "companies" / "keyword-corp" / "enrichments"
    company_dir.mkdir(parents=True)
    (company_dir / "website.md").write_text(
        "---\nurl: https://keywordcorp.com\nfound_keywords:\n  - vinyl\n  - epoxy\n---\n",
        encoding="utf-8",
    )

    result = export_enriched_emails(CAMPAIGN)

    assert result.exported_count == 1
    assert result.output_csv is not None
    content = result.output_csv.read_text()
    assert "vinyl" in content and "epoxy" in content


def test_no_category_and_no_keywords_is_skipped(tmp_path: Path) -> None:
    _setup(tmp_path)
    _write_checkpoint(tmp_path, [
        _prospect("ChIJFFFFFFFFFFFFFFFFFFFFFFF", "bare-corp", "Bare Corp", "barecorp.com", category=None),
    ])
    _write_email_shard(tmp_path, "info@barecorp.com", "barecorp.com", "bare-corp")

    result = export_enriched_emails(CAMPAIGN)

    assert result.exported_count == 0
    assert result.skipped_count == 1


def test_keywords_flag_requires_actual_found_keywords(tmp_path: Path) -> None:
    _setup(tmp_path)
    _write_checkpoint(tmp_path, [
        _prospect("ChIJGGGGGGGGGGGGGGGGGGGGGGG", "category-only-corp", "Category Only Corp", "categoryonly.com", category="Flooring contractor"),
    ])
    _write_email_shard(tmp_path, "info@categoryonly.com", "categoryonly.com", "category-only-corp")
    # No website.md - no found_keywords, only has a checkpoint category.

    result = export_enriched_emails(CAMPAIGN, keywords=True)

    assert result.exported_count == 0, "category alone must not satisfy --keywords"


def test_no_checkpoint_raises(tmp_path: Path) -> None:
    _setup(tmp_path)
    import pytest

    with pytest.raises(FileNotFoundError):
        export_enriched_emails(CAMPAIGN)
