"""op_purge_to_call (2026-08-31): Mark had to clear stale to-call entries
while compile-to-call's population logic is still being refined, and the
only existing purge logic was inline inside op_compile_to_call's --purge
flag - gated behind the full (slower) compact+identify+repopulate
workflow, with no standalone way to just clear the queue. Extracted into
OperationService._purge_to_call_pending_files(), shared by both the
inline step and this new standalone operation.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cocli.application.operation_service import OperationService
from cocli.core.paths import paths
from cocli.models.search import SearchResult


@pytest.fixture
def pending_to_call_dir(tmp_path: Path):
    with patch.object(paths, "root", tmp_path):
        pending = paths.campaign("test-campaign").path / "queues" / "to-call" / "pending"
        pending.mkdir(parents=True)
        yield pending


def test_op_purge_to_call_is_registered() -> None:
    service = OperationService(campaign_name="test-campaign")
    details = service.get_details("op_purge_to_call")
    assert details is not None
    assert details.title == "Purge To-Call Queue"
    assert details.category == "maintenance"
    assert "op_purge_to_call" in {op.id for op in service.list_operations()}


@pytest.mark.asyncio
async def test_op_purge_to_call_deletes_pending_files(pending_to_call_dir: Path) -> None:
    (pending_to_call_dir / "a.usv").write_text("x")
    (pending_to_call_dir / "b.usv").write_text("x")

    service = OperationService(campaign_name="test-campaign")
    result = await service.execute("op_purge_to_call")

    assert result["status"] == "success"
    assert result["result"]["purged"] == 2
    assert list(pending_to_call_dir.glob("*.usv")) == []


@pytest.mark.asyncio
async def test_op_purge_to_call_is_a_noop_on_an_empty_queue(
    pending_to_call_dir: Path,
) -> None:
    service = OperationService(campaign_name="test-campaign")
    result = await service.execute("op_purge_to_call")

    assert result["status"] == "success"
    assert result["result"]["purged"] == 0


@pytest.mark.asyncio
async def test_op_purge_to_call_only_deletes_to_call_files(
    pending_to_call_dir: Path,
) -> None:
    """Regression guard: the shared helper is scoped to
    queues/to-call/pending/ specifically - it must never reach into a
    sibling queue (gm-list, gm-details, enrichment)."""
    (pending_to_call_dir / "a.usv").write_text("x")
    # pending_to_call_dir = .../queues/to-call/pending, so parents[1] is
    # .../queues - the sibling gm-list queue lives at .../queues/gm-list.
    gm_list_pending = pending_to_call_dir.parents[1] / "gm-list" / "pending"
    gm_list_pending.mkdir(parents=True)
    (gm_list_pending / "keep.usv").write_text("x")

    service = OperationService(campaign_name="test-campaign")
    await service.execute("op_purge_to_call")

    assert list(pending_to_call_dir.glob("*.usv")) == []
    assert (gm_list_pending / "keep.usv").exists()


@pytest.mark.asyncio
async def test_op_compile_to_call_tags_new_companies_with_campaign_name(
    tmp_path: Path,
) -> None:
    """Regression (Mark, 2026-08-31): op_compile_to_call's "create new
    company from prospect" branch built a bare Company() with no tags at
    all, so anything created through this path was invisible to
    audit_campaign_integrity (which only inspects companies where
    campaign_name is in company.tags) - discovered while investigating why
    ~6,055 roadmap prospects have no companies/<slug> directory."""
    prospect = SearchResult(
        type="company",
        unique_id="acme-financial",
        display="Acme Financial",
        slug="acme-financial",
        domain="acmefinancial.com",
        average_rating=4.5,
        reviews_count=10,
        tags=[],
    )

    captured_company = {}

    def fake_create_company_files(
        company: object, company_dir: object, rebuild_cache: bool = True
    ) -> object:
        captured_company["company"] = company
        return company_dir

    with patch.object(paths, "root", tmp_path), patch(
        "cocli.application.search_service.get_fuzzy_search_results",
        return_value=[prospect],
    ), patch(
        "cocli.core.email_index_manager.EmailIndexManager.compact",
        return_value=None,
    ), patch(
        "cocli.models.companies.company.Company.get", return_value=None
    ), patch(
        "cocli.core.utils.create_company_files",
        side_effect=fake_create_company_files,
    ), patch(
        "cocli.models.base.write_queue_files", return_value=None
    ), patch(
        "cocli.core.cache.build_cache", return_value=None
    ):
        service = OperationService(campaign_name="test-campaign")
        result = await service.execute("op_compile_to_call")

    assert result["status"] == "success"
    created_company = captured_company["company"]
    assert "test-campaign" in created_company.campaigns
    assert "test-campaign" not in created_company.tags


@pytest.mark.asyncio
async def test_op_compile_to_call_dry_run_writes_nothing(tmp_path: Path) -> None:
    """Regression (Mark, 2026-09-01): op_compile_to_call had no way to
    preview what it would do without actually writing companies/queue
    files - the only verification available was mocked unit tests, never a
    real run. --dry-run should still do the real (read-only) lead lookup
    but skip every write: compaction, company create/update, the --purge
    delete, and the queue write."""
    new_prospect = SearchResult(
        type="company",
        unique_id="new-co",
        display="New Co",
        slug="new-co",
        domain="newco.com",
        average_rating=4.5,
        reviews_count=10,
        tags=[],
    )
    existing_prospect = SearchResult(
        type="company",
        unique_id="existing-co",
        display="Existing Co",
        slug="existing-co",
        domain="existingco.com",
        average_rating=3.0,
        reviews_count=5,
        tags=[],
    )
    existing_company = MagicMock(tags=["test-campaign"], average_rating=3.0, reviews_count=5, name="Existing Co")

    def fake_company_get(slug: str) -> object:
        return existing_company if slug == "existing-co" else None

    with patch.object(paths, "root", tmp_path), patch(
        "cocli.application.search_service.get_fuzzy_search_results",
        return_value=[new_prospect, existing_prospect],
    ), patch(
        "cocli.core.email_index_manager.EmailIndexManager.compact"
    ) as mock_compact, patch(
        "cocli.models.companies.company.Company.get", side_effect=fake_company_get
    ), patch(
        "cocli.core.utils.create_company_files"
    ) as mock_create, patch(
        "cocli.models.base.write_queue_files"
    ) as mock_write_queue, patch(
        "cocli.core.cache.build_cache"
    ) as mock_build_cache:
        service = OperationService(campaign_name="test-campaign")
        result = await service.execute(
            "op_compile_to_call", params={"dry_run": True, "purge": True}
        )

    assert result["status"] == "success"
    op_result = result["result"]
    assert op_result["dry_run"] is True
    assert op_result["would_create_count"] == 1
    assert op_result["would_update_count"] == 1
    assert op_result["would_enqueue_count"] == 2
    assert set(op_result["sample_slugs"]) == {"new-co", "existing-co"}

    mock_compact.assert_not_called()
    mock_create.assert_not_called()
    mock_write_queue.assert_not_called()
    mock_build_cache.assert_not_called()
    existing_company.save.assert_not_called()


@pytest.mark.asyncio
async def test_op_compile_to_call_add_more_skips_pending_and_do_not_call(
    tmp_path: Path,
) -> None:
    """Regression (Mark, 2026-09-01): "add more" is the standard population
    strategy - running compile-to-call again while some tasks are still
    pending must not re-add them (wasted rewrite) or resurrect anyone on
    the shared do-not-call list. Both checks happen before any company
    write, so a skip costs nothing."""
    from cocli.core.do_not_call_manager import DoNotCallManager

    already_pending = SearchResult(
        type="company",
        unique_id="already-pending-co",
        display="Already Pending Co",
        slug="already-pending-co",
        domain="alreadypending.com",
        average_rating=5.0,
        reviews_count=100,
        tags=[],
    )
    do_not_call = SearchResult(
        type="company",
        unique_id="dnc-co",
        display="DNC Co",
        slug="dnc-co",
        domain="dncco.com",
        phone_number="512-234-5678",
        average_rating=4.9,
        reviews_count=90,
        tags=[],
    )
    excluded = SearchResult(
        type="company",
        unique_id="excluded-co",
        display="Excluded Co",
        slug="excluded-co",
        domain="excludedco.com",
        average_rating=4.7,
        reviews_count=70,
        tags=[],
    )
    fresh = SearchResult(
        type="company",
        unique_id="fresh-co",
        display="Fresh Co",
        slug="fresh-co",
        domain="freshco.com",
        average_rating=4.8,
        reviews_count=80,
        tags=[],
    )

    with patch.object(paths, "root", tmp_path):
        pending_dir = paths.campaign("test-campaign").path / "queues" / "to-call" / "pending"
        pending_dir.mkdir(parents=True)
        (pending_dir / "already-pending-co.usv").write_text("stale content")

        DoNotCallManager().add("512-234-5678")
        from cocli.core.exclusions import ExclusionManager

        ExclusionManager("test-campaign").add_exclusion(
            slug="excluded-co", domain="excludedco.com", reason="to-call-nonconforming"
        )

        with patch(
            "cocli.application.search_service.get_fuzzy_search_results",
            return_value=[already_pending, do_not_call, excluded, fresh],
        ), patch(
            "cocli.core.email_index_manager.EmailIndexManager.compact"
        ), patch(
            "cocli.models.companies.company.Company.get", return_value=None
        ) as mock_get, patch(
            "cocli.core.utils.create_company_files"
        ) as mock_create, patch(
            "cocli.models.base.write_queue_files"
        ) as mock_write_queue, patch(
            "cocli.core.cache.build_cache"
        ):
            service = OperationService(campaign_name="test-campaign")
            result = await service.execute("op_compile_to_call", params={})

    assert result["status"] == "success"
    op_result = result["result"]
    assert op_result["created_count"] == 1
    assert op_result["skipped_already_pending"] == 1
    assert op_result["skipped_do_not_call"] == 1
    assert op_result["skipped_excluded"] == 1

    # Only fresh-co should ever have been looked up/created - the others
    # were skipped before any company or queue write.
    mock_get.assert_called_once_with("fresh-co")
    mock_create.assert_called_once()
    created_company = mock_create.call_args.args[0]
    assert created_company.slug == "fresh-co"
    mock_write_queue.assert_called_once()
    items = mock_write_queue.call_args.kwargs["items"]
    assert [t.company_slug for t in items] == ["fresh-co"]

    # The already-pending file must not have been rewritten.
    with patch.object(paths, "root", tmp_path):
        pending_dir = paths.campaign("test-campaign").path / "queues" / "to-call" / "pending"
        assert (pending_dir / "already-pending-co.usv").read_text() == "stale content"
