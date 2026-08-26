# POLICY: frictionless-data-policy-enforcement
"""Companies-tab TEMPLATES must query Frictionless indexes via DuckDB."""

from pathlib import Path
from typing import Any, Iterator, List, Set

import pytest

import cocli.application.search_service as search_service
from cocli.application.search_service import (
    get_fuzzy_search_results,
    get_template_counts,
)
from cocli.core.cache import build_cache
from cocli.core.paths import paths
from cocli.models.campaigns.indexes.email import EmailEntry
from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
from cocli.models.search import SearchResult


CAMPAIGN = "test/templates"


@pytest.fixture
def reset_search_state() -> Iterator[None]:
    search_service._con = None
    search_service._counts_cache.clear()
    search_service._last_campaign = None
    search_service._last_cache_mtime = -1.0
    search_service._last_checkpoint_mtime = -1.0
    search_service._last_venue_mtime = -1.0
    search_service._last_lifecycle_mtime = -1.0
    search_service._last_to_call_mtime = -1.0
    if hasattr(search_service, "_last_email_mtime"):
        search_service._last_email_mtime = -1.0
    yield
    search_service._con = None
    search_service._counts_cache.clear()


def _write_company_md(slug: str, name: str, extra: str = "") -> None:
    comp_dir = paths.companies / slug
    comp_dir.mkdir(parents=True, exist_ok=True)
    (comp_dir / "_index.md").write_text(
        f"---\nname: {name}\ntags:\n  - {CAMPAIGN}\n{extra}---\n"
    )


def _prospect(
    *,
    slug: str,
    name: str,
    place_suffix: str,
    phone: str | None = None,
    street: str | None = None,
    rating: float | None = None,
    reviews: int | None = None,
    domain: str | None = None,
) -> GoogleMapsProspect:
    payload: dict[str, Any] = {
        "place_id": f"ChIJ{place_suffix}aaaaaaaaaaaaaa",
        "company_slug": slug,
        "name": name,
        "phone": phone,
        "street_address": street,
        "city": "Austin" if street else None,
        "state": "TX" if street else None,
        "zip": "78701" if street else None,
        "average_rating": rating,
        "reviews_count": reviews,
        "domain": domain,
    }
    return GoogleMapsProspect.model_validate(payload)


@pytest.fixture
def templates_env(
    mock_cocli_env: Path, mocker: Any, reset_search_state: None
) -> str:
    """Companies whose email lives in the emails index, not markdown."""
    campaign_node = paths.campaign(CAMPAIGN)
    prospect_idx = campaign_node.index("google_maps_prospects")
    prospect_idx.path.mkdir(parents=True, exist_ok=True)

    prospects = [
        _prospect(
            slug="email-co",
            name="Email Co",
            place_suffix="emailco",
            phone="5125551111",
            street="123 Main St",
            rating=4.8,
            reviews=100,
            domain="emailco.com",
        ),
        _prospect(
            slug="inbox-co",
            name="Inbox Co",
            place_suffix="inboxco",
            phone="5125552222",
            street="45 Oak Ave",
            rating=4.2,
            reviews=20,
            domain="inboxco.com",
        ),
        _prospect(
            slug="no-email-co",
            name="No Email Co",
            place_suffix="noemail",
            phone="5125553333",
            street=None,
            rating=3.1,
            reviews=8,
            domain="noemailco.com",
        ),
        _prospect(
            slug="no-contact-co",
            name="No Contact Co",
            place_suffix="nocontact",
            phone=None,
            street="9 Pine Rd",
            rating=4.9,
            reviews=250,
            domain="nocontact.com",
        ),
        _prospect(
            slug="legacy-md-co",
            name="Legacy Md Co",
            place_suffix="legacymd",
            phone="5125554444",
            street="7 Elm St",
            rating=4.0,
            reviews=12,
            domain="legacymd.com",
        ),
    ]
    with open(prospect_idx.checkpoint, "w", encoding="utf-8") as f:
        for p in prospects:
            f.write(p.to_usv())
    GoogleMapsProspect.write_datapackage(CAMPAIGN)

    emails_root = campaign_node.index("emails").path
    shards_dir = emails_root / "shards"
    inbox_dir = emails_root / "inbox" / "ab"
    shards_dir.mkdir(parents=True, exist_ok=True)
    inbox_dir.mkdir(parents=True, exist_ok=True)

    shard_entry = EmailEntry(
        email="hello@emailco.com",
        domain="emailco.com",
        company_slug="email-co",
        source="website_scraper",
    )
    (shards_dir / "aa.usv").write_text(shard_entry.to_usv(), encoding="utf-8")

    inbox_entry = EmailEntry(
        email="team@inboxco.com",
        domain="inboxco.com",
        company_slug="inbox-co",
        source="website_scraper",
    )
    (inbox_dir / "team@inboxco.com.usv").write_text(
        inbox_entry.to_usv(), encoding="utf-8"
    )

    EmailEntry.save_datapackage(
        emails_root, "emails", "shards/*.usv", force=True
    )

    _write_company_md("email-co", "Email Co", "domain: emailco.com\n")
    _write_company_md("inbox-co", "Inbox Co", "domain: inboxco.com\n")
    _write_company_md("no-email-co", "No Email Co", "domain: noemailco.com\n")
    _write_company_md("no-contact-co", "No Contact Co", "domain: nocontact.com\n")
    _write_company_md(
        "legacy-md-co",
        "Legacy Md Co",
        "domain: legacymd.com\nemail: owner@legacymd.com\n",
    )

    mocker.patch("cocli.core.config.get_campaign", return_value=CAMPAIGN)
    mocker.patch("cocli.application.search_service.get_campaign", return_value=CAMPAIGN)
    build_cache(campaign=CAMPAIGN)
    return CAMPAIGN


def _slugs(results: List[SearchResult]) -> Set[str]:
    return {slug for r in results if (slug := r.slug)}


def test_has_email_includes_index_and_cache_emails(templates_env: str) -> None:
    results = get_fuzzy_search_results(
        "",
        campaign_name=templates_env,
        filters={"has_email": True},
        force_rebuild_cache=True,
    )
    assert _slugs(results) == {"email-co", "inbox-co", "legacy-md-co"}


def test_no_email_excludes_index_and_cache_emails(templates_env: str) -> None:
    results = get_fuzzy_search_results(
        "",
        campaign_name=templates_env,
        filters={"no_email": True},
        force_rebuild_cache=True,
    )
    assert _slugs(results) == {"no-email-co", "no-contact-co"}


def test_actionable_requires_email_and_phone(templates_env: str) -> None:
    results = get_fuzzy_search_results(
        "",
        campaign_name=templates_env,
        filters={"has_email_and_phone": True},
        force_rebuild_cache=True,
    )
    assert _slugs(results) == {"email-co", "inbox-co", "legacy-md-co"}


def test_no_address_uses_checkpoint_street(templates_env: str) -> None:
    results = get_fuzzy_search_results(
        "",
        campaign_name=templates_env,
        filters={"no_address": True},
        force_rebuild_cache=True,
    )
    assert _slugs(results) == {"no-email-co"}


def test_top_rated_sorts_by_rating_desc(templates_env: str) -> None:
    results = get_fuzzy_search_results(
        "",
        campaign_name=templates_env,
        sort_by="rating",
        force_rebuild_cache=True,
    )
    assert [r.slug for r in results][0] == "no-contact-co"
    ratings = [r.average_rating or 0.0 for r in results]
    assert ratings == sorted(ratings, reverse=True)


def test_most_reviewed_sorts_by_reviews_desc(templates_env: str) -> None:
    results = get_fuzzy_search_results(
        "",
        campaign_name=templates_env,
        sort_by="reviews",
        force_rebuild_cache=True,
    )
    assert [r.slug for r in results][0] == "no-contact-co"
    reviews = [r.reviews_count or 0 for r in results]
    assert reviews == sorted(reviews, reverse=True)


def test_template_counts_cover_all_company_templates(templates_env: str) -> None:
    get_fuzzy_search_results(
        "", campaign_name=templates_env, force_rebuild_cache=True
    )
    counts = get_template_counts(campaign_name=templates_env)
    assert counts["tpl_all"] == 5
    assert counts["tpl_with_email"] == 3
    assert counts["tpl_no_email"] == 2
    assert counts["tpl_actionable"] == 3
    assert counts["tpl_no_address"] == 1
    assert counts["tpl_top_rated"] == 4  # rating >= 4.0
    assert counts["tpl_most_reviewed"] == 4  # reviews >= 10
    assert counts.get("tpl_to_call", 0) == 0
