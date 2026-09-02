"""Retrofits person names onto already-indexed emails, for campaigns that
were enriched before the FIRST_NAMES dictionary gate was relaxed
(cocli/enrichment/website_scraper.py::infer_name_from_dotted_mailbox).

Needs no re-scraping and no cached HTML: a firstname.lastname@domain shape
is fully present in the email address itself, already sitting in
EmailIndexManager. Uses the exact same inference function the live scraper
uses (WebsiteScraper.infer_name_from_dotted_mailbox / GENERIC_MAILBOX_PREFIXES)
so this can never silently drift from the production heuristic.

Writes updated entries back to the hot inbox (EmailIndexManager.add_email) -
run `cocli data compact-emails` afterward to fold them into shards.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel

from ..core.email_index_manager import EmailIndexManager
from ..enrichment.website_scraper import GENERIC_MAILBOX_PREFIXES, WebsiteScraper
from ..models.campaigns.indexes.email import EmailEntry


class RetrofitResult(BaseModel):
    campaign_name: str
    dry_run: bool
    scanned: int = 0
    matched: int = 0
    sample_names: list[str] = []


def retrofit_personnel_names(
    campaign_name: str, dry_run: bool = True, sample_limit: int = 10
) -> RetrofitResult:
    """Scans every currently-untagged email in `campaign_name`'s index and
    backfills a person: tag wherever the mailbox shape now yields a name.

    Naturally idempotent and safe to re-run: matched entries get a person:
    tag, so a second pass's `tags NOT LIKE '%person:%'` filter excludes them.
    """
    manager = EmailIndexManager(campaign_name)
    scraper = WebsiteScraper(processed_by="email_personnel_retrofit")

    # Empty tags serialize to an empty CSV field, which DuckDB's read_csv
    # treats as NULL, not ''. "tags NOT LIKE ..." on a NULL evaluates to
    # NULL (excluded by WHERE, not included) - the common case of an
    # entry with no tags at all would be silently skipped without the
    # explicit IS NULL branch.
    candidates = manager.query(sql_where="tags IS NULL OR tags NOT LIKE '%person:%'")

    result = RetrofitResult(campaign_name=campaign_name, dry_run=dry_run)
    for entry in candidates:
        result.scanned += 1
        mailbox = str(entry.email).split("@", 1)[0]
        if mailbox.lower() in GENERIC_MAILBOX_PREFIXES:
            continue

        inferred = scraper.infer_name_from_dotted_mailbox(mailbox)
        if not inferred:
            continue

        result.matched += 1
        if len(result.sample_names) < sample_limit:
            result.sample_names.append(inferred["name"])

        if dry_run:
            continue

        new_tags = list(entry.tags)
        new_tags.append(f"person:{inferred['name']}")
        if "name_confidence" in inferred:
            new_tags.append(f"name_confidence:{inferred['name_confidence']}")

        updated = EmailEntry(
            email=entry.email,
            domain=entry.domain,
            company_slug=entry.company_slug,
            source=entry.source,
            found_at=entry.found_at,
            first_seen=entry.first_seen,
            # Bump last_seen so this write deterministically wins the LWW
            # fold on next compact - re-adding with an unchanged last_seen
            # leaves DuckDB's row_number() tie-break undefined.
            last_seen=datetime.now(UTC),
            verification_status=entry.verification_status,
            tags=new_tags,
        )
        manager.add_email(updated)

    return result
