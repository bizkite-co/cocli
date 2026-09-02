"""Unit tests for Website.save()'s merge-with-existing behavior.

A force_refresh re-scrape that comes back sparse or fails must not blank
out previously-good enrichment data - force_refresh means "try again," not
"erase what we had." See task-agent ticket
website.save-blindly-overwrites-website.md-on-every-enrichment-write-no-merge-safety-against-sparse-force-refresh-scrapes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cocli.core.paths import paths
from cocli.models.companies.website import Website


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths.root = tmp_path
    monkeypatch.delenv("COCLI_CAMPAIGN", raising=False)


def _website_md_path(slug: str) -> Path:
    return paths.companies.ensure() / slug / "enrichments" / "website.md"


def _read_frontmatter(slug: str) -> dict:
    import yaml

    from cocli.core.text_utils import parse_frontmatter

    content = _website_md_path(slug).read_text(encoding="utf-8")
    fm = parse_frontmatter(content)
    assert fm is not None
    return yaml.safe_load(fm)


def test_sparse_refresh_does_not_blank_previously_good_fields() -> None:
    slug = "acme-flooring"

    good = Website(
        url="acme-flooring.com",
        phone="+15551234567",
        description="A real flooring contractor.",
        categories=["Flooring contractor"],
        found_keywords=["flooring", "carpet"],
    )
    good.save(slug)

    sparse = Website(url="acme-flooring.com")
    sparse.save(slug)

    data = _read_frontmatter(slug)
    assert data["phone"] == "15551234567"
    assert data["description"] == "A real flooring contractor."
    assert data["categories"] == ["Flooring contractor"]
    assert data["found_keywords"] == ["flooring", "carpet"]


def test_fresh_non_empty_value_overwrites_existing() -> None:
    slug = "acme-flooring"

    Website(url="acme-flooring.com", description="Old description.").save(slug)
    Website(url="acme-flooring.com", description="New, better description.").save(slug)

    data = _read_frontmatter(slug)
    assert data["description"] == "New, better description."


def test_fresh_false_is_not_treated_as_hollow() -> None:
    slug = "acme-flooring"

    Website(url="acme-flooring.com", is_email_provider=True).save(slug)
    Website(url="acme-flooring.com", is_email_provider=False).save(slug)

    data = _read_frontmatter(slug)
    assert data["is_email_provider"] is False


def test_error_field_always_reflects_latest_attempt_not_stale_existing() -> None:
    """A previous failed attempt's error must not resurrect itself once a
    later attempt succeeds cleanly - error describes the latest outcome,
    not accumulated history."""
    slug = "acme-flooring"

    Website(url="acme-flooring.com", error="navigation_failed").save(slug)
    Website(url="acme-flooring.com", description="Found it this time.").save(slug)

    data = _read_frontmatter(slug)
    assert "error" not in data
    assert data["description"] == "Found it this time."


def test_first_save_with_no_existing_file_just_writes_fresh_data() -> None:
    slug = "brand-new-company"

    Website(url="brand-new-company.com", phone="+15559876543").save(slug)

    data = _read_frontmatter(slug)
    assert data["phone"] == "15559876543"


def test_sparse_refresh_does_not_shrink_list_fields() -> None:
    """A fresh non-empty list is not proof it's at least as complete as
    the existing one - the old field-level hollow-check let a smaller
    fresh list silently discard existing entries not present in it."""
    slug = "acme-flooring"

    Website(
        url="acme-flooring.com",
        categories=["Flooring Contractor", "Home Improvement", "Carpet Store"],
        all_emails=["jane@acme.com", "info@acme.com", "sales@acme.com"],
    ).save(slug)

    Website(url="acme-flooring.com", categories=["Flooring Contractor"], all_emails=["info@acme.com"]).save(slug)

    data = _read_frontmatter(slug)
    assert set(data["categories"]) == {"Flooring Contractor", "Home Improvement", "Carpet Store"}
    assert set(data["all_emails"]) == {"jane@acme.com", "info@acme.com", "sales@acme.com"}


def test_list_field_union_still_adds_genuinely_new_entries() -> None:
    slug = "acme-flooring"

    Website(url="acme-flooring.com", categories=["Flooring Contractor"]).save(slug)
    Website(url="acme-flooring.com", categories=["Flooring Contractor", "Carpet Store"]).save(slug)

    data = _read_frontmatter(slug)
    assert set(data["categories"]) == {"Flooring Contractor", "Carpet Store"}


def test_personnel_entries_merge_fields_within_a_matched_identity() -> None:
    """Personnel is List[Dict] - a fresh entry with just a name for
    someone already on file with a title+email must not blank those
    fields, and must not create a duplicate entry for the same person."""
    slug = "acme-flooring"

    Website(
        url="acme-flooring.com",
        personnel=[{"name": "Jane Doe", "title": "Owner", "email": "jane@acme.com"}],
    ).save(slug)

    Website(url="acme-flooring.com", personnel=[{"name": "Jane Doe"}, {"name": "Bob Smith"}]).save(slug)

    data = _read_frontmatter(slug)
    assert len(data["personnel"]) == 2
    jane = next(p for p in data["personnel"] if p["name"] == "Jane Doe")
    assert jane["title"] == "Owner"
    assert jane["email"] == "jane@acme.com"
    assert any(p["name"] == "Bob Smith" for p in data["personnel"])


def _screenshot_path(slug: str) -> Path:
    return paths.companies.ensure() / slug / "enrichments" / "screenshot.png"


def test_screenshot_bytes_written_to_sidecar_not_frontmatter() -> None:
    slug = "acme-flooring"
    fake_png = b"\x89PNG\r\n\x1a\nfake-image-bytes"

    Website(url="acme-flooring.com", screenshot_bytes=fake_png).save(slug)

    assert _screenshot_path(slug).read_bytes() == fake_png
    data = _read_frontmatter(slug)
    assert "screenshot_bytes" not in data


def test_missing_screenshot_on_rescrape_does_not_delete_existing_one() -> None:
    """A sparse/failed screenshot capture on a re-scrape (e.g. a
    force_refresh that navigated fine but the screenshot call itself
    errored) must not wipe out a previously-captured good screenshot -
    same merge-safety principle as every other field."""
    slug = "acme-flooring"
    fake_png = b"\x89PNG\r\n\x1a\nfake-image-bytes"

    Website(url="acme-flooring.com", screenshot_bytes=fake_png).save(slug)
    assert _screenshot_path(slug).exists()

    # Re-scrape with no screenshot captured this time.
    Website(url="acme-flooring.com", description="updated description").save(slug)

    assert _screenshot_path(slug).read_bytes() == fake_png


def test_enrichment_error_writes_dated_http_note() -> None:
    slug = "adams-insurance"
    Website(
        url="adamsinsuranceagency.net",
        error="Navigation failed with status 404",
        error_category="navigation_failed",
        http_status=404,
    ).save(slug)

    notes_dir = paths.companies.ensure() / slug / "notes"
    notes = list(notes_dir.glob("*website-http-404.md"))
    assert len(notes) == 1
    body = notes[0].read_text()
    assert "HTTP 404" in body
    assert "adamsinsuranceagency.net" in body
    assert "mark invalid" in body.lower()
