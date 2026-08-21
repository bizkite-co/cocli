"""Unit tests for WebsiteScraper's personnel-name extraction confidence gate.

The `firstname.lastname@domain` and Owner/Founder-context heuristics used to
hard-require the first name to be in a ~200-entry FIRST_NAMES dictionary,
silently dropping real names outside it (uncommon spellings, non-English
names). Both heuristics already have a strong non-dictionary signal of their
own (email shape / job-title adjacency), so the dictionary requirement is now
a confidence signal (tagged `name_confidence: heuristic` when unmatched)
rather than a hard gate.
"""

from bs4 import BeautifulSoup

from cocli.enrichment.website_scraper import WebsiteScraper
from cocli.models.companies.website import Website


def _scraper() -> WebsiteScraper:
    return WebsiteScraper(processed_by="test")


def _website(**overrides: object) -> Website:
    return Website(url="example.com", **overrides)  # type: ignore[arg-type]


def test_dictionary_first_name_email_pattern_still_matches_with_no_confidence_tag() -> None:
    scraper = _scraper()
    website = _website()
    soup = BeautifulSoup("<p>Contact john.smith@example.com for a quote.</p>", "html.parser")

    scraper._extract_personnel(soup, website)

    assert len(website.personnel) == 1
    entry = website.personnel[0]
    assert entry["name"] == "John Smith"
    assert "name_confidence" not in entry


def test_non_dictionary_first_name_email_pattern_now_matches_with_heuristic_tag() -> None:
    scraper = _scraper()
    website = _website()
    # "Keeley" is a real, uncommon-spelling first name not in FIRST_NAMES.
    soup = BeautifulSoup("<p>Contact keeley.watkins@example.com for a quote.</p>", "html.parser")

    scraper._extract_personnel(soup, website)

    assert len(website.personnel) == 1
    entry = website.personnel[0]
    assert entry["name"] == "Keeley Watkins"
    assert entry["name_confidence"] == "heuristic"


def test_generic_mailbox_prefix_still_excluded() -> None:
    scraper = _scraper()
    website = _website()
    soup = BeautifulSoup("<p>Email info.desk@example.com anytime.</p>", "html.parser")

    scraper._extract_personnel(soup, website)

    assert website.personnel == []


def test_owner_context_pattern_with_non_dictionary_name_now_matches() -> None:
    scraper = _scraper()
    website = _website()
    soup = BeautifulSoup("<p>Owner: Zbigniew Kowalski has run this shop since 1998.</p>", "html.parser")

    scraper._extract_personnel(soup, website)

    matches = [p for p in website.personnel if p["name"] == "Zbigniew Kowalski"]
    assert len(matches) == 1
    assert matches[0]["name_confidence"] == "heuristic"
    assert matches[0]["title"] == "Owner"


def test_owner_context_pattern_with_dictionary_name_has_no_confidence_tag() -> None:
    scraper = _scraper()
    website = _website()
    soup = BeautifulSoup("<p>Founder: John Anderson started the company in 2001.</p>", "html.parser")

    scraper._extract_personnel(soup, website)

    matches = [p for p in website.personnel if p["name"] == "John Anderson"]
    assert len(matches) == 1
    assert "name_confidence" not in matches[0]


def test_index_emails_propagates_heuristic_confidence_tag() -> None:
    scraper = _scraper()
    website = _website(
        associated_company_folder="acme",
        personnel=[
            {"name": "Keeley Watkins", "email": "keeley.watkins@example.com", "name_confidence": "heuristic"},
            {"name": "John Smith", "email": "john.smith@example.com"},
        ],
    )

    added = []

    class _FakeIndexManager:
        def __init__(self, campaign_name: str) -> None:
            pass

        def add_email(self, entry: object) -> None:
            added.append(entry)

    import cocli.enrichment.website_scraper as mod
    original = mod.EmailIndexManager
    mod.EmailIndexManager = _FakeIndexManager  # type: ignore[assignment,misc]
    try:
        scraper._index_emails(website, campaign_name="test-campaign")
    finally:
        mod.EmailIndexManager = original  # type: ignore[misc]

    by_email = {e.email: e for e in added if getattr(e, "source", "") == "website_scraper_personnel"}
    assert "name_confidence:heuristic" in by_email["keeley.watkins@example.com"].tags
    assert "name_confidence:heuristic" not in by_email["john.smith@example.com"].tags
