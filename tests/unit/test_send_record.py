from __future__ import annotations

from datetime import datetime, UTC
from typing import Any

from cocli.models.send_record import SendRecord


def _record(**overrides: Any) -> SendRecord:
    defaults: dict[str, Any] = dict(
        guid="abc123",
        campaign_name="roadmap",
        initiative="testimonials",
        company_slug="acme-co",
        template_id="request_testimonial.md",
        recipient_email="bob@acme.test",
        subject="Hi Bob",
        sent_at=datetime(2026, 10, 3, tzinfo=UTC),
    )
    defaults.update(overrides)
    return SendRecord(**defaults)


def test_save_creates_a_hash_sharded_file(tmp_path: Any, monkeypatch: Any) -> None:
    """The actual point: lots of independently-keyed send records,
    sharded to avoid one giant directory - same convention as domains/
    and the email inbox, not a new structural concept."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    record = _record()
    path = record.save()

    expected_shard = SendRecord.shard_for("abc123")
    assert path == tmp_path / "campaigns" / "roadmap" / "sends" / expected_shard / "abc123.md"
    assert path.exists()


def test_get_round_trips_the_saved_record(tmp_path: Any, monkeypatch: Any) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    _record().save()

    loaded = SendRecord.get("roadmap", "abc123")
    assert loaded is not None
    assert loaded.company_slug == "acme-co"
    assert loaded.recipient_email == "bob@acme.test"


def test_get_returns_none_when_no_record_exists(tmp_path: Any, monkeypatch: Any) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    assert SendRecord.get("roadmap", "nonexistent-guid") is None


def test_mark_clicked_sets_timestamp_once_and_increments_count(tmp_path: Any, monkeypatch: Any) -> None:
    record = _record()
    assert record.clicked_at is None
    assert record.click_count == 0

    record.mark_clicked()
    first_click = record.clicked_at
    assert first_click is not None
    assert record.click_count == 1

    record.mark_clicked()
    # clicked_at is the FIRST click, not the most recent - click_count
    # tracks how many, this field tracks when it started.
    assert record.clicked_at == first_click
    assert record.click_count == 2


def test_mark_unsubscribed_sets_timestamp_and_optional_reason() -> None:
    record = _record()
    assert record.unsubscribed_at is None

    record.mark_unsubscribed(reason="too many emails")

    assert record.unsubscribed_at is not None
    assert record.unsubscribe_reason == "too many emails"


def test_two_different_sends_to_the_same_company_get_independent_records(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """The actual gap this replaces: rendered-outreach/<company>/<template>
    is overwritten by a later send of the same template, losing the
    earlier send's history. Two SendRecords for the same company+template
    but different guids must both persist independently."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    first = _record(guid="guid-one", subject="First send")
    second = _record(guid="guid-two", subject="Second send (template was edited)")
    first.save()
    second.save()

    loaded_first = SendRecord.get("roadmap", "guid-one")
    loaded_second = SendRecord.get("roadmap", "guid-two")
    assert loaded_first is not None and loaded_first.subject == "First send"
    assert loaded_second is not None and loaded_second.subject == "Second send (template was edited)"
