import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from cocli.application.company_service import (
    backfill_missing_companies_from_prospects,
    get_company_details_for_view,
)
from cocli.core.importing import apply_prospect_to_company_if_empty
from cocli.core.paths import paths
from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
from cocli.models.companies.company import Company
from cocli.models.company_name import CompanyName


def _prospect(slug: str, name: str) -> GoogleMapsProspect:
    return GoogleMapsProspect(
        place_id=f"ChIJ-test-place-id-{slug}-0000000000",
        slug=slug,
        name=CompanyName(name),
        average_rating=4.5,
        reviews_count=10,
        domain=f"{slug}.com",
    )


@pytest.fixture
def sandboxed_companies_dir(tmp_path: Path):
    with patch.object(paths, "root", tmp_path):
        companies_dir = paths.companies.path
        companies_dir.mkdir(parents=True, exist_ok=True)
        yield companies_dir


def test_dry_run_reports_but_does_not_write(sandboxed_companies_dir: Path) -> None:
    with patch(
        "cocli.core.prospects_csv_manager.ProspectsIndexManager.read_all_prospects",
        return_value=[_prospect("missing-co", "Missing Co")],
    ):
        result = backfill_missing_companies_from_prospects("test-campaign", dry_run=True)

    assert result["missing_count"] == 1
    assert result["created_count"] == 0
    assert not (sandboxed_companies_dir / "missing-co").exists()


def test_execute_creates_directory_tagged_with_campaign_and_provenance_marker(
    sandboxed_companies_dir: Path,
) -> None:
    with patch(
        "cocli.core.prospects_csv_manager.ProspectsIndexManager.read_all_prospects",
        return_value=[_prospect("missing-co", "Missing Co")],
    ):
        result = backfill_missing_companies_from_prospects("test-campaign", dry_run=False)

    assert result["created_count"] == 1
    company_dir = sandboxed_companies_dir / "missing-co"
    assert company_dir.exists()
    index_text = (company_dir / "_index.md").read_text()
    assert "test-campaign" in index_text
    assert result["tag"] in index_text


def test_skips_prospects_that_already_have_a_company_directory(
    sandboxed_companies_dir: Path,
) -> None:
    company_dir = sandboxed_companies_dir / "already-here"
    company_dir.mkdir()
    (company_dir / "_index.md").write_text("---\nname: Already Here\n---\n")

    with patch(
        "cocli.core.prospects_csv_manager.ProspectsIndexManager.read_all_prospects",
        return_value=[_prospect("already-here", "Already Here")],
    ):
        result = backfill_missing_companies_from_prospects("test-campaign", dry_run=False)

    assert result["missing_count"] == 0
    assert result["created_count"] == 0


def test_backfills_a_bare_directory_with_no_index_md(
    sandboxed_companies_dir: Path,
) -> None:
    """Regression (Mark, 2026-08-31): the enrichment worker's
    Website.save() creates companies/<slug>/enrichments/ via
    mkdir(parents=True) for slugs with no company yet, leaving a bare
    directory with no _index.md (126 found in production). That's not a
    real company record - Company.from_directory() treats it the same as
    missing - so it must not be skipped as "already exists"."""
    shell_dir = sandboxed_companies_dir / "enrichment-shell-only"
    (shell_dir / "enrichments").mkdir(parents=True)
    (shell_dir / "enrichments" / "website.md").write_text("---\ndomain: shell.com\n---\n")

    with patch(
        "cocli.core.prospects_csv_manager.ProspectsIndexManager.read_all_prospects",
        return_value=[_prospect("enrichment-shell-only", "Enrichment Shell Only")],
    ):
        result = backfill_missing_companies_from_prospects("test-campaign", dry_run=False)

    assert result["created_count"] == 1
    assert (shell_dir / "_index.md").exists()


def test_min_hours_since_last_run_skips_a_fresh_marker(sandboxed_companies_dir: Path) -> None:
    """Regression (Mark, 2026-09-01): a login-triggered run (systemd
    OnStartupSec=, fires every login) needs to no-op if it already ran
    recently, rather than re-scanning every prospect on every login."""
    with patch(
        "cocli.core.prospects_csv_manager.ProspectsIndexManager.read_all_prospects",
        return_value=[_prospect("missing-co", "Missing Co")],
    ):
        first = backfill_missing_companies_from_prospects(
            "test-campaign", dry_run=False, min_hours_since_last_run=20
        )
        assert first["created_count"] == 1
        assert first["skipped_stale_check"] is False

        second = backfill_missing_companies_from_prospects(
            "test-campaign", dry_run=False, min_hours_since_last_run=20
        )

    assert second["skipped_stale_check"] is True
    assert second["hours_since_last_run"] < 20


def test_min_hours_since_last_run_runs_once_marker_is_old_enough(sandboxed_companies_dir: Path) -> None:
    from cocli.core.paths import paths

    marker_path = paths.campaign("test-campaign").path / ".backfill-from-prospects-last-run"
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text("stale")
    old_time = time.time() - (25 * 3600)
    os.utime(marker_path, (old_time, old_time))

    with patch(
        "cocli.core.prospects_csv_manager.ProspectsIndexManager.read_all_prospects",
        return_value=[_prospect("missing-co", "Missing Co")],
    ):
        result = backfill_missing_companies_from_prospects(
            "test-campaign", dry_run=False, min_hours_since_last_run=20
        )

    assert result["skipped_stale_check"] is False
    assert result["created_count"] == 1


def test_min_hours_since_last_run_ignored_for_dry_run(sandboxed_companies_dir: Path) -> None:
    from cocli.core.paths import paths

    marker_path = paths.campaign("test-campaign").path / ".backfill-from-prospects-last-run"
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text("fresh")

    with patch(
        "cocli.core.prospects_csv_manager.ProspectsIndexManager.read_all_prospects",
        return_value=[_prospect("missing-co", "Missing Co")],
    ):
        result = backfill_missing_companies_from_prospects(
            "test-campaign", dry_run=True, min_hours_since_last_run=20
        )

    assert result["skipped_stale_check"] is False
    assert result["missing_count"] == 1


def test_view_overlays_domain_from_maps_enrichment(
    sandboxed_companies_dir: Path,
) -> None:
    slug = "adams-insurance-agency"
    company_dir = sandboxed_companies_dir / slug
    enrich = company_dir / "enrichments"
    enrich.mkdir(parents=True)
    (company_dir / "_index.md").write_text(
        "---\n"
        "name: Adams Insurance Agency\n"
        f"slug: {slug}\n"
        "place_id: ChIJQ1A68rPbyYkR_dONAUWyrRo\n"
        "street_address: 474 Prospect Blvd\n"
        "city: Frederick\n"
        "---\n"
    )
    from cocli.core.constants import UNIT_SEP

    header = UNIT_SEP.join(
        [
            "place_id",
            "slug",
            "name",
            "domain",
            "website",
            "gmb_url",
            "average_rating",
            "reviews_count",
            "updated_at",
        ]
    )
    row = UNIT_SEP.join(
        [
            "ChIJQ1A68rPbyYkR_dONAUWyrRo",
            slug,
            "Adams Insurance Agency",
            "adamsinsuranceagency.net",
            "http://www.adamsinsuranceagency.net/",
            "https://www.google.com/maps/place/Adams+Insurance/",
            "4.9",
            "305",
            "2026-09-02T18:25:49+00:00",
        ]
    )
    (enrich / "google_maps.usv").write_text(header + "\n" + row + "\n")

    with patch(
        "cocli.application.company_service.WebsiteCache"
    ) as mock_cache:
        mock_cache.return_value.get_by_url.return_value = None
        details = get_company_details_for_view(slug)
    assert details is not None
    assert details["company"]["domain"] == "adamsinsuranceagency.net"
    assert "query=google" not in (details["company"].get("gmb_url") or "")
    assert "maps/place" in (details["company"].get("gmb_url") or "")


def test_view_lists_website_emails_in_contacts(
    sandboxed_companies_dir: Path,
) -> None:
    slug = "hot-lead-co"
    company_dir = sandboxed_companies_dir / slug
    enrich = company_dir / "enrichments"
    enrich.mkdir(parents=True)
    (company_dir / "_index.md").write_text(
        f"---\nname: Hot Lead Co\nslug: {slug}\n---\n"
    )
    (enrich / "website.md").write_text(
        "---\n"
        "url: hotlead.com\n"
        "email: info@hotlead.com\n"
        "all_emails:\n"
        "- info@hotlead.com\n"
        "- sales@hotlead.com\n"
        "- email@example.com\n"
        "- bssvpr@fhzzreftvyypcn.pbz\n"
        "personnel:\n"
        "- name: Jane Doe\n"
        "  email: jane@hotlead.com\n"
        "  title: Owner\n"
        "email_contexts:\n"
        "  sales@hotlead.com: Sales\n"
        "---\n"
    )

    with patch(
        "cocli.application.company_service.WebsiteCache"
    ) as mock_cache:
        mock_cache.return_value.get_by_url.return_value = None
        details = get_company_details_for_view(slug)

    assert details is not None
    emails = {str(c.get("email")) for c in details["contacts"]}
    assert emails == {"info@hotlead.com", "sales@hotlead.com", "jane@hotlead.com"}
    assert "email@example.com" not in emails
    assert "bssvpr@fhzzreftvyypcn.pbz" not in emails
    jane = next(c for c in details["contacts"] if c["email"] == "jane@hotlead.com")
    assert jane["name"] == "Jane Doe"
    assert jane["role"] == "Owner"
    assert details["company"]["email"] == "info@hotlead.com"
    assert "sales@hotlead.com" in [str(e) for e in details["company"]["all_emails"]]


def test_list_known_contacts_includes_company_email_and_personnel(
    sandboxed_companies_dir: Path,
) -> None:
    from cocli.application.company_service import format_contact_line, list_known_contacts

    slug = "aquila-financial-tax-services"
    company_dir = sandboxed_companies_dir / slug
    enrich = company_dir / "enrichments"
    enrich.mkdir(parents=True)
    (company_dir / "_index.md").write_text(
        "---\n"
        "name: Aquila Financial\n"
        f"slug: {slug}\n"
        "email: info@aftaxservices.com\n"
        "all_emails:\n"
        "- info@aftaxservices.com\n"
        "---\n"
    )
    (enrich / "website.md").write_text(
        "---\n"
        "url: aftaxservices.com\n"
        "email: info@aftaxservices.com\n"
        "personnel:\n"
        "- name: James Aquila\n"
        "  title: Founder\n"
        "---\n"
    )

    contacts = list_known_contacts(slug)
    names = {str(c.get("name") or "") for c in contacts}
    emails = {str(c.get("email") or "") for c in contacts}
    assert "James Aquila" in names
    assert "info@aftaxservices.com" in emails
    lines = [format_contact_line(c) for c in contacts]
    assert any("James Aquila" in line and "Founder" in line for line in lines)
    assert any("info@aftaxservices.com" in line for line in lines)


def test_hydrate_fills_empty_domain_without_overwriting(
    sandboxed_companies_dir: Path,
) -> None:
    company = Company(name=CompanyName("Acme"), slug="acme")
    company.save(rebuild_cache=False)
    assert Company.get("acme") is not None
    assert Company.get("acme").domain is None

    prospect = GoogleMapsProspect(
        place_id="ChIJ-test-place-id-acme-0000000000",
        slug="acme",
        name=CompanyName("Acme"),
        domain="acme.com",
        website="http://acme.com",
    )
    assert apply_prospect_to_company_if_empty(prospect) is True
    loaded = Company.get("acme")
    assert loaded is not None
    assert loaded.domain == "acme.com"
    assert loaded.website_url == "http://acme.com"

    other = GoogleMapsProspect(
        place_id="ChIJ-test-place-id-acme-0000000000",
        slug="acme",
        name=CompanyName("Acme"),
        domain="other.com",
        website="http://other.com",
    )
    apply_prospect_to_company_if_empty(other)
    loaded = Company.get("acme")
    assert loaded is not None
    assert loaded.domain == "acme.com"
    assert loaded.website_url == "http://acme.com"


def test_get_company_activity(sandboxed_companies_dir: Path) -> None:
    from datetime import UTC, datetime, timedelta
    from cocli.application.company_service import get_company_activity
    from cocli.models.companies.call_note import CallNote
    from cocli.models.companies.email_note import EmailNote
    from cocli.models.companies.meeting import Meeting
    from cocli.models.companies.note import Note

    company_slug = "activity-test-co"
    co_dir = sandboxed_companies_dir / company_slug
    notes_dir = co_dir / "notes"
    meetings_dir = co_dir / "meetings"
    notes_dir.mkdir(parents=True)
    meetings_dir.mkdir(parents=True)

    t_now = datetime.now(UTC)

    # 1. Email note sent 1 hour ago
    email_note = EmailNote(
        timestamp=t_now - timedelta(hours=1),
        title="Proposal Details",
        direction="sent",
        from_address="sales@example.com",
        to_addresses=["client@activity.com"],
        content="Here is the proposal we promised.",
    )
    email_note.to_file(notes_dir)

    # 2. Call logged via CallNote 2 hours ago
    call_time = t_now - timedelta(hours=2)
    call_note = CallNote(
        timestamp=call_time,
        title="Call Log: Follow Up Needed",
        disposition="Follow Up Needed",
        phone="555-123-4567",
        content="Great conversation with the owner.",
    )
    call_note.to_file(notes_dir)

    # 3. Duplicate Meeting logged at same call time (what CallLogModal does)
    meeting_call = Meeting(
        timestamp=call_time + timedelta(seconds=2),
        title="Logged Call: Follow Up Needed",
        type="phone-call",
        content="Disposition: Follow Up Needed\n\nGreat conversation with the owner.",
    )
    meeting_call.to_file(meetings_dir)

    # 4. General note 3 hours ago
    gen_note = Note(
        timestamp=t_now - timedelta(hours=3),
        title="Internal research",
        content="Company has 15 employees.",
    )
    gen_note.to_file(notes_dir)

    # 5. In-person meeting 1 day ago
    calendar_meeting = Meeting(
        timestamp=t_now - timedelta(days=1),
        title="Initial Consultation",
        type="in-person",
        content="Met at their downtown office.",
    )
    calendar_meeting.to_file(meetings_dir)

    activities = get_company_activity(company_slug)

    # Assert that call was deduplicated (4 distinct activities total)
    assert len(activities) == 4

    # Assert order is newest first
    assert activities[0].activity_type == "email"
    assert activities[0].icon == "✉"
    assert "Proposal Details" in activities[0].title

    assert activities[1].activity_type == "call"
    assert activities[1].icon == "📞"
    assert activities[1].metadata.get("disposition") == "Follow Up Needed"

    assert activities[2].activity_type == "note"
    assert activities[2].icon == "📝"

    assert activities[3].activity_type == "meeting"
    assert activities[3].icon == "📅"
    assert activities[3].title == "Initial Consultation"
