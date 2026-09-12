"""Email/domain index paths come from StationDecl combinators (0010 PR4).

Shard key is the domain. Hashing the email address would miss live inbox files.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from cocli.core.domain_index_manager import DomainIndexManager
from cocli.core.email_index_manager import EmailIndexManager
from cocli.models.campaigns.indexes.domains import WebsiteDomainCsv
from cocli.models.campaigns.indexes.email import EmailEntry
from cocli.station_defs.campaigns.indexes import DOMAIN_HASH_SHARD
from cocli.station_defs.campaigns.indexes.domains import DOMAIN_INBOX
from cocli.station_defs.campaigns.indexes.emails import EMAIL_INBOX, EMAIL_SHARDS
from cocli.station_defs.path_helpers import (
    domain_inbox_leaf,
    domain_shard_id,
    email_inbox_rel,
    email_shard_file_rel,
    email_shard_id,
)
from stations.segments import collect_shard


def _legacy_domain_hash(domain: str) -> str:
    return hashlib.sha256(domain.encode()).hexdigest()[:2]


def test_email_and_domain_decls_share_domain_hash_combinator() -> None:
    assert collect_shard(EMAIL_INBOX.segments) is DOMAIN_HASH_SHARD
    assert collect_shard(EMAIL_SHARDS.segments) is DOMAIN_HASH_SHARD
    assert collect_shard(DOMAIN_INBOX.segments) is DOMAIN_HASH_SHARD
    assert email_shard_id("example.com") == _legacy_domain_hash("example.com")
    assert domain_shard_id("example.com") == email_shard_id("example.com")
    assert email_shard_id("example.com") != email_shard_id("a@example.com")


def test_email_inbox_rel_is_inbox_domain_hash_email() -> None:
    rel = email_inbox_rel("a@example.com.usv", domain="example.com")
    assert rel == f"inbox/{_legacy_domain_hash('example.com')}/a@example.com.usv"
    assert email_shard_file_rel("example.com") == (
        f"shards/{_legacy_domain_hash('example.com')}.usv"
    )


def test_email_index_manager_add_email_uses_decl_path(
    tmp_path: Path, monkeypatch: Any
) -> None:
    camp_dir = tmp_path / "campaigns" / "camp"
    camp_dir.mkdir(parents=True)
    monkeypatch.setattr(
        "cocli.core.email_index_manager.get_campaign_dir",
        lambda _name: camp_dir,
    )
    mgr = EmailIndexManager("camp")
    entry = EmailEntry(email="A@Example.com", domain="example.com", source="test")
    assert mgr.add_email(entry)
    expected = camp_dir / "indexes" / "emails" / email_inbox_rel(
        "a@example.com.usv", domain="example.com"
    )
    assert expected.is_file()
    assert mgr.get_shard_id("example.com") == _legacy_domain_hash("example.com")


def test_domain_index_manager_inbox_key_uses_decl_leaf() -> None:
    campaign = MagicMock()
    campaign.name = "test-campaign"
    with patch("cocli.core.config.load_campaign_config") as mock_config, patch(
        "cocli.core.reporting.get_boto3_session"
    ) as mock_session:
        mock_config.return_value = {"aws": {"data_bucket_name": "test-bucket"}}
        mock_session.return_value.client.return_value = MagicMock()
        manager = DomainIndexManager(campaign, use_cloud=True)
        manager.s3_client = MagicMock()
        item = WebsiteDomainCsv(
            domain="test-atomic-index.com",
            company_name="Test USV Inc",
            updated_at=datetime.now(UTC),
        )
        manager.add_or_update(item)
        leaf = domain_inbox_leaf(
            "test-atomic-index.com", filename="test-atomic-index.com.usv"
        )
        key = manager.s3_client.put_object.call_args[1]["Key"]
        assert key == f"indexes/domains/inbox/{leaf}"
        assert manager.get_shard_id("test-atomic-index.com") == _legacy_domain_hash(
            "test-atomic-index.com"
        )
