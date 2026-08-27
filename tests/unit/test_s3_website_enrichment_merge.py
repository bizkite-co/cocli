"""Unit tests for S3CompanyManager.save_website_enrichment()'s merge-safety.

Website.save() (the local write) was already fixed to merge against
existing data instead of blindly overwriting - see task-agent ticket
website.save-blindly-overwrites-website.md-on-every-enrichment-write-no-merge-safety-against-sparse-force-refresh-scrapes.
The S3 mirror write went through a separate, unguarded `put_object` and
was never covered by that fix, so local and S3 copies of the same
website.md could silently diverge. These tests cover the fix that wires
the S3 path through the same shared merge helper Website.save() uses.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from cocli.core.paths import paths
from cocli.core.s3_company_manager import S3CompanyManager
from cocli.models.companies.website import Website


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths.root = tmp_path
    monkeypatch.delenv("COCLI_CAMPAIGN", raising=False)


def _manager_with_mock_s3() -> tuple[S3CompanyManager, MagicMock]:
    """Bypass __init__ (which needs real AWS/campaign config) - only
    save_website_enrichment's own logic is under test here."""
    manager = S3CompanyManager.__new__(S3CompanyManager)
    manager.s3_bucket_name = "test-bucket"
    manager.s3_client = MagicMock()
    return manager, manager.s3_client


def _put_object_body_yaml(mock_s3_client: MagicMock) -> dict:
    kwargs = mock_s3_client.put_object.call_args.kwargs
    body = kwargs["Body"].decode("utf-8")
    return yaml.safe_load(body.strip("-\n"))


@pytest.mark.asyncio
async def test_sparse_scrape_does_not_blank_field_already_good_locally() -> None:
    slug = "acme-flooring"

    # A previously-good local save (mirrors what the enrichment worker
    # already wrote to disk before this S3 push runs).
    Website(url="acme-flooring.com", phone="+15551234567", description="A real flooring contractor.").save(slug)

    manager, mock_s3 = _manager_with_mock_s3()
    sparse = Website(url="acme-flooring.com", error="timeout")

    await manager.save_website_enrichment(slug, sparse)

    data = _put_object_body_yaml(mock_s3)
    assert data["phone"] == "15551234567"
    assert data["description"] == "A real flooring contractor."
    assert data["error"] == "timeout"  # error itself never merges from existing


@pytest.mark.asyncio
async def test_fresh_non_empty_value_still_overwrites() -> None:
    slug = "acme-flooring"

    Website(url="acme-flooring.com", description="Old description.").save(slug)

    manager, mock_s3 = _manager_with_mock_s3()
    fresh = Website(url="acme-flooring.com", description="New, better description.")

    await manager.save_website_enrichment(slug, fresh)

    data = _put_object_body_yaml(mock_s3)
    assert data["description"] == "New, better description."


@pytest.mark.asyncio
async def test_no_local_file_yet_just_pushes_fresh_data() -> None:
    slug = "brand-new-company"

    manager, mock_s3 = _manager_with_mock_s3()
    fresh = Website(url="brand-new-company.com", phone="+15559876543")

    await manager.save_website_enrichment(slug, fresh)

    data = _put_object_body_yaml(mock_s3)
    assert data["phone"] == "15559876543"
