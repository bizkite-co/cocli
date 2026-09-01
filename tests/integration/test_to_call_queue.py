"""Integration test for to-call queue population."""

import pytest

from cocli.models.campaigns.queues.to_call import ToCallTask
from cocli.core.paths import paths
from cocli.core.config import set_campaign
from cocli.application.search_service import get_fuzzy_search_results


@pytest.fixture
def to_call_integration_env(tmp_path, monkeypatch):
    """Set up a test environment with companies that have ratings and reviews."""
    monkeypatch.setenv("COCLI_ENV", "test")

    data_home = tmp_path / "cocli_data"
    data_home.mkdir()
    monkeypatch.setattr(paths, "root", data_home)

    campaign = "test-to-call-int"
    set_campaign(campaign)

    # Create campaign directory structure
    campaign_path = data_home / "campaigns" / campaign
    campaign_path.mkdir(parents=True)

    queues_path = campaign_path / "queues"
    queues_path.mkdir()

    # Create companies with ratings and reviews
    companies = [
        {
            "slug": "company-with-rating-1",
            "name": "High Rating Company",
            "domain": "high.example.com",
            "email": "contact@high.example.com",
            "average_rating": 4.8,
            "reviews_count": 150,
            "tags": [campaign],
        },
        {
            "slug": "company-with-rating-2",
            "name": "Good Rating Company",
            "domain": "good.example.com",
            "email": "info@good.example.com",
            "average_rating": 4.6,
            "reviews_count": 80,
            "tags": [campaign],
        },
        {
            "slug": "company-no-contact",
            "name": "No Contact Company",
            "domain": "no-contact.example.com",
            "average_rating": 4.9,
            "reviews_count": 200,
            "tags": [campaign],
        },
    ]

    companies_dir = data_home / "companies"
    companies_dir.mkdir(parents=True)

    for company in companies:
        company_dir = companies_dir / company["slug"]
        company_dir.mkdir(parents=True)

        # Create _index.md
        frontmatter_lines = [f"tags: [{campaign}]"]
        frontmatter_lines.extend(
            f"{k}: {v}"
            for k, v in company.items()
            if k not in ("slug", "tags") and v is not None
        )

        content = "---\n" + "\n".join(frontmatter_lines) + "\n---\n"
        (company_dir / "_index.md").write_text(content, encoding="utf-8")

    return campaign, companies


def test_to_call_queue_population(to_call_integration_env):
    """Test that the to-call queue gets populated with companies having ratings and contact info."""
    campaign, companies = to_call_integration_env

    # Step 1: Build search cache
    results = get_fuzzy_search_results(
        "",
        item_type="company",
        campaign_name=campaign,
        force_rebuild_cache=True,
    )

    # Should find all companies
    assert len(results) >= len(companies), (
        f"Expected at least {len(companies)} results, got {len(results)}"
    )

    # Step 2: Filter for companies with contact info and ratings
    results_with_contact = get_fuzzy_search_results(
        "",
        item_type="company",
        campaign_name=campaign,
        filters={"has_contact_info": True},
    )

    # Should find only companies with email or phone
    assert len(results_with_contact) >= 1, (
        "Should find at least 1 company with contact info"
    )

    # Step 3: Verify results have average_rating and reviews_count
    results_with_rating = [
        r
        for r in results_with_contact
        if r.average_rating is not None and r.reviews_count is not None
    ]

    assert len(results_with_rating) >= 1, (
        "Should find at least 1 company with rating and reviews"
    )

    # Step 4: Test ToCallTask creation and saving
    top_prospect = results_with_rating[0]

    task = ToCallTask(
        company_slug=top_prospect.slug,
        domain=top_prospect.domain or "unknown",
        campaign_name=campaign,
        ack_token=None,
    )

    task_path = task.get_local_path()

    # Verify path is in the correct location
    assert "to-call" in str(task_path), f"Path should contain 'to-call': {task_path}"
    assert "pending" in str(task_path), f"Path should contain 'pending': {task_path}"

    # Save the task
    task.save()

    # Verify file was created
    assert task_path.exists(), f"Task file should exist at {task_path}"

    # Verify file content
    content = task_path.read_text(encoding="utf-8")
    assert top_prospect.slug in content, (
        f"Task file should contain slug: {content[:100]}"
    )

    # Step 5: Verify task can be found by get_fuzzy_search_results with to_call filter
    to_call_results = get_fuzzy_search_results(
        "",
        filters={"to_call": True},
        campaign_name=campaign,
    )

    assert len(to_call_results) >= 1, "Should find at least 1 to-call task"


def test_to_call_task_path_resolution(to_call_integration_env):
    """Test that ToCallTask path resolution works correctly."""
    campaign, _ = to_call_integration_env

    task1 = ToCallTask(
        company_slug="test-company",
        domain="test.com",
        campaign_name=campaign,
        ack_token=None,
    )

    # Unscheduled task should go to pending/
    path1 = task1.get_local_path()
    assert "pending" in str(path1), f"Unscheduled task should be in pending: {path1}"
    assert "test-company.usv" in str(path1), (
        f"Path should contain company slug: {path1}"
    )

    # A scheduled follow-up (callback_at set) also goes to pending/ now -
    # Mark, 2026-09-01: the old separate scheduled/YYYY/MM/DD/ directory was
    # never read back by anything, so a scheduled follow-up silently
    # vanished once its date arrived. callback_at is the due date, checked
    # by whatever reads the queue, not encoded in the path.
    from datetime import datetime

    task2 = ToCallTask(
        company_slug="test-company-2",
        domain="test.com",
        campaign_name=campaign,
        ack_token=None,
        callback_at=datetime(2026, 3, 30, 12, 30),
    )

    path2 = task2.get_local_path()
    assert "pending" in str(path2), f"Scheduled task should also be in pending: {path2}"
    assert "test-company-2.usv" in str(path2), (
        f"Path should contain company slug: {path2}"
    )


def test_a_future_scheduled_task_does_not_show_as_due_yet(to_call_integration_env):
    """Regression (Mark, 2026-09-01): a pending task with a future
    callback_at is a scheduled follow-up, not something due right now -
    is_to_call/the to_call filter must not surface it until its date
    arrives, otherwise "add more" would treat it as already-pending
    correctly, but anything reading "what's due today" would call it too
    early."""
    from datetime import datetime, timedelta, UTC

    campaign, _ = to_call_integration_env

    due_now = ToCallTask(
        company_slug="company-with-rating-1",
        domain="high.example.com",
        campaign_name=campaign,
        ack_token=None,
    )
    due_now.save()

    not_due_yet = ToCallTask(
        company_slug="company-with-rating-2",
        domain="good.example.com",
        campaign_name=campaign,
        ack_token=None,
        callback_at=datetime.now(UTC) + timedelta(days=30),
    )
    not_due_yet.save()

    to_call_results = get_fuzzy_search_results(
        "",
        filters={"to_call": True},
        campaign_name=campaign,
        force_rebuild_cache=True,
    )
    due_slugs = {r.slug for r in to_call_results}

    assert "company-with-rating-1" in due_slugs
    assert "company-with-rating-2" not in due_slugs
