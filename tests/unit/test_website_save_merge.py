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
