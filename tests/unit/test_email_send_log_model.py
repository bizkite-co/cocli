"""SendLogEntry must own its own datapackage.json, same as LeadFilterEntry."""

import json

from cocli.models.campaigns.indexes.email_send_log import SendLogEntry


def test_to_usv_from_usv_roundtrip() -> None:
    entry = SendLogEntry(
        batch_id="20260914T000000Z",
        template_id="email_01_pas_hook.md",
        company_slug="acme-financial",
        recipient="bob@acme.test",
        subject="Hi Bob",
        message_id="ses-123",
        status="sent",
    )
    parsed = SendLogEntry.from_usv(entry.to_usv())
    assert parsed.batch_id == entry.batch_id
    assert parsed.company_slug == entry.company_slug
    assert parsed.recipient == entry.recipient
    assert parsed.status == "sent"
    assert parsed.message_id == "ses-123"


def test_get_index_dir_is_campaign_scoped(mock_cocli_env, mocker) -> None:
    from cocli.core.paths import paths

    dir_a = SendLogEntry.get_index_dir("roadmap")
    dir_b = SendLogEntry.get_index_dir("turboship")
    assert dir_a != dir_b
    assert dir_a == paths.campaign("roadmap").index("email-send-log").path


def test_save_datapackage_writes_schema(mock_cocli_env, mocker) -> None:
    index_dir = SendLogEntry.get_index_dir("roadmap")
    index_dir.mkdir(parents=True, exist_ok=True)

    SendLogEntry.save_datapackage(index_dir, "email_send_log", "log.usv")

    dp = json.loads((index_dir / "datapackage.json").read_text())
    resource_names = {r["name"] for r in dp["resources"]}
    assert resource_names == {"email_send_log"}
