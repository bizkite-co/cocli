from datetime import datetime, UTC

from cocli.models.campaigns.indexes.domains import WebsiteDomainCsv


def test_naive_updated_at_is_coerced_to_utc() -> None:
    item = WebsiteDomainCsv(
        domain="millvalley.bairdwealth.com",
        updated_at=datetime(2026, 9, 2, 12, 0, 0),
    )
    assert item.updated_at.tzinfo is not None
    assert item.updated_at.tzinfo == UTC
