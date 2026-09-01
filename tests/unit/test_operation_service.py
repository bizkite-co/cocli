"""op_purge_to_call (2026-08-31): Mark had to clear stale to-call entries
while compile-to-call's population logic is still being refined, and the
only existing purge logic was inline inside op_compile_to_call's --purge
flag - gated behind the full (slower) compact+identify+repopulate
workflow, with no standalone way to just clear the queue. Extracted into
OperationService._purge_to_call_pending_files(), shared by both the
inline step and this new standalone operation.
"""

from pathlib import Path
from unittest.mock import patch

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
    assert "test-campaign" in created_company.tags
