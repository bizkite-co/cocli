"""FollowUpTask must support more than one pending entry per company -
the whole reason it's not just another field on ToCallTask, whose file
path is keyed by company_slug alone (one pending file per company)."""

from __future__ import annotations

import json
from datetime import datetime, UTC

from cocli.models.campaigns.queues.follow_up import FollowUpTask


def _task(**overrides: object) -> FollowUpTask:
    defaults = dict(
        company_slug="acme-financial",
        domain="acme.test",
        campaign_name="roadmap",
        scheduled_at=datetime(2026, 9, 20, tzinfo=UTC),
        format="email",
        template_id="email_02_screenshots.md",
        initiative="rta",
    )
    defaults.update(overrides)
    return FollowUpTask(**defaults)  # type: ignore[arg-type]


def test_to_usv_from_usv_roundtrip() -> None:
    task = _task()
    parsed = FollowUpTask.from_usv(task.to_usv())
    assert parsed.company_slug == task.company_slug
    assert parsed.format == "email"
    assert parsed.template_id == "email_02_screenshots.md"
    assert parsed.initiative == "rta"
    assert parsed.scheduled_at == task.scheduled_at


def test_two_follow_ups_for_the_same_company_get_different_paths(mock_cocli_env) -> None:
    """The actual bug ToCallTask can't fix: a second scheduled follow-up
    for the same company must not overwrite the first."""
    first = _task()
    second = _task(format="call", template_id=None)

    assert first.get_local_path() != second.get_local_path()

    first.save()
    second.save()

    assert first.get_local_path().exists()
    assert second.get_local_path().exists()


def test_call_format_has_no_template(mock_cocli_env) -> None:
    task = _task(format="call", template_id=None)
    parsed = FollowUpTask.from_usv(task.to_usv())
    assert parsed.format == "call"
    assert parsed.template_id is None


def test_save_writes_datapackage(mock_cocli_env) -> None:
    from cocli.core.paths import paths

    task = _task()
    task.save()

    base_queue = paths.campaign("roadmap").path / "queues" / "follow-up"
    dp_path = base_queue / "datapackage.json"
    assert dp_path.exists()
    dp = json.loads(dp_path.read_text())
    resource_names = {r["name"] for r in dp["resources"]}
    assert resource_names == {"follow_up_queue"}
