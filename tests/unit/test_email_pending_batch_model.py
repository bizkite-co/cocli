"""PendingBatchEntry must own its own datapackage.json, same as
SendLogEntry/LeadFilterEntry, and must round-trip multi-line body text."""

import json

from cocli.models.campaigns.indexes.email_pending_batch import PendingBatchEntry


def test_to_usv_from_usv_roundtrip() -> None:
    entry = PendingBatchEntry(
        batch_id="20260915T000000000000Z",
        template_id="email_01_pas_hook.md",
        company_slug="acme-financial",
        recipient="bob@acme.test",
        subject="Hi Bob",
        body="Line one\nLine two",
    )
    parsed = PendingBatchEntry.from_usv(entry.to_usv())
    assert parsed.batch_id == entry.batch_id
    assert parsed.company_slug == entry.company_slug
    assert parsed.recipient == entry.recipient
    assert parsed.subject == entry.subject
    # to_usv() sanitizes newlines to "<br>" (base.py's generic USV string
    # encoding) - from_usv() gives that back verbatim, not real newlines.
    # Un-escaping is the caller's job (see
    # PersonalizedOutreachService._entry_to_match) - this test documents
    # that raw round-trip, so a future change to that encoding is noticed.
    assert parsed.body == "Line one<br>Line two"


def test_get_index_dir_is_campaign_scoped(mock_cocli_env, mocker) -> None:
    from cocli.core.paths import paths

    dir_a = PendingBatchEntry.get_index_dir("roadmap")
    dir_b = PendingBatchEntry.get_index_dir("turboship")
    assert dir_a != dir_b
    assert dir_a == paths.campaign("roadmap").index("email-pending-batch").path


def test_save_datapackage_writes_schema(mock_cocli_env, mocker) -> None:
    index_dir = PendingBatchEntry.get_index_dir("roadmap")
    index_dir.mkdir(parents=True, exist_ok=True)

    PendingBatchEntry.save_datapackage(index_dir, "email_pending_batch", "pending.usv")

    dp = json.loads((index_dir / "datapackage.json").read_text())
    resource_names = {r["name"] for r in dp["resources"]}
    assert resource_names == {"email_pending_batch"}
