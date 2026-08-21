"""Unit tests for the offline personnel-name retrofit pass
(cocli/application/email_personnel_retrofit.py) - the no-re-scrape path
that backfills person: tags onto already-indexed emails using the same
inference function the live scraper uses."""

from pathlib import Path

from cocli.application.email_personnel_retrofit import retrofit_personnel_names
from cocli.core.email_index_manager import EmailIndexManager
from cocli.core.paths import paths
from cocli.models.campaigns.indexes.email import EmailEntry


def _seed(campaign: str, email: str, domain: str, tags: list[str] | None = None) -> None:
    manager = EmailIndexManager(campaign)
    manager.add_email(
        EmailEntry(
            email=email,
            domain=domain,
            company_slug="acme",
            source="website_scraper",
            tags=tags or [],
        )
    )


def test_dry_run_reports_matches_without_writing(tmp_path: Path) -> None:
    paths.root = tmp_path
    campaign = "test-campaign"
    _seed(campaign, "keeley.watkins@example.com", "example.com")

    result = retrofit_personnel_names(campaign, dry_run=True)

    assert result.scanned == 1
    assert result.matched == 1
    assert result.sample_names == ["Keeley Watkins"]

    # No tag written back - re-running finds the same untagged candidate.
    again = retrofit_personnel_names(campaign, dry_run=True)
    assert again.scanned == 1
    assert again.matched == 1


def test_apply_writes_person_tag_and_is_idempotent(tmp_path: Path) -> None:
    paths.root = tmp_path
    campaign = "test-campaign"
    _seed(campaign, "keeley.watkins@example.com", "example.com")

    result = retrofit_personnel_names(campaign, dry_run=False)
    assert result.matched == 1

    manager = EmailIndexManager(campaign)
    entries = manager.query()
    assert len(entries) == 1
    assert any(t == "person:Keeley Watkins" for t in entries[0].tags)
    assert any(t == "name_confidence:heuristic" for t in entries[0].tags)

    # Second pass finds nothing left to do - already tagged.
    again = retrofit_personnel_names(campaign, dry_run=False)
    assert again.scanned == 0
    assert again.matched == 0


def test_dictionary_name_gets_no_confidence_tag(tmp_path: Path) -> None:
    paths.root = tmp_path
    campaign = "test-campaign"
    _seed(campaign, "john.smith@example.com", "example.com")

    retrofit_personnel_names(campaign, dry_run=False)

    entries = EmailIndexManager(campaign).query()
    assert any(t == "person:John Smith" for t in entries[0].tags)
    assert not any(t.startswith("name_confidence:") for t in entries[0].tags)


def test_generic_mailbox_prefix_and_already_tagged_are_skipped(tmp_path: Path) -> None:
    paths.root = tmp_path
    campaign = "test-campaign"
    _seed(campaign, "info@example.com", "example.com")
    _seed(campaign, "already.tagged@example.com", "example.com", tags=["person:Already Tagged"])

    result = retrofit_personnel_names(campaign, dry_run=False)

    # info@ is scanned (no person: tag yet) but excluded by the generic-
    # mailbox denylist; already.tagged@ is excluded from the query itself
    # (it already has a person: tag), so only 1 candidate is ever scanned.
    assert result.scanned == 1
    assert result.matched == 0
