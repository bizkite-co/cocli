"""EmailEventsService.poll(): SQS -> SesEventLogEntry, plus auto-suppress
on permanent bounces/complaints. Mirrors EmailService.poll()'s test
shape (fake client instead of the real boto3 SQS client)."""

from __future__ import annotations

import json
from typing import Any

from cocli.application.email_events_service import EmailEventsService
from cocli.models.campaigns.indexes.ses_event_log import SesEventLogEntry


def _sns_envelope(event: dict[str, Any]) -> str:
    return json.dumps({"Type": "Notification", "Message": json.dumps(event)})


def _bounce_event(message_id: str, recipient: str, bounce_type: str = "Permanent") -> dict[str, Any]:
    return {
        "eventType": "Bounce",
        "mail": {"messageId": message_id, "destination": [recipient]},
        "bounce": {"bounceType": bounce_type},
    }


def _complaint_event(message_id: str, recipient: str) -> dict[str, Any]:
    return {
        "eventType": "Complaint",
        "mail": {"messageId": message_id, "destination": [recipient]},
        "complaint": {"complaintFeedbackType": "abuse"},
    }


class FakeSqs:
    def __init__(self, messages: list[dict[str, Any]]) -> None:
        self._messages = [
            {"Body": body, "ReceiptHandle": f"rh-{i}"} for i, body in enumerate(messages)
        ]
        self.deleted: list[str] = []

    def get_queue_url(self, QueueName: str) -> dict[str, str]:
        return {"QueueUrl": f"https://sqs.test/{QueueName}"}

    def receive_message(self, **kwargs: Any) -> dict[str, Any]:
        return {"Messages": self._messages}

    def delete_message(self, *, QueueUrl: str, ReceiptHandle: str) -> None:
        self.deleted.append(ReceiptHandle)


def test_permanent_bounce_is_recorded_and_suppressed(mock_cocli_env, mocker) -> None:
    mock_suppress = mocker.patch(
        "cocli.application.ses_suppression_service.SesSuppressionService.suppress_email",
        return_value=True,
    )
    sqs = FakeSqs([_sns_envelope(_bounce_event("msg-1", "bad@co.test"))])

    service = EmailEventsService("test-campaign", region="us-west-1", sqs_client=sqs)
    result = service.poll(limit=10)

    assert result.fetched == 1
    assert result.recorded == 1
    assert result.ignored == 0
    assert result.suppressed == ["bad@co.test"]
    assert sqs.deleted == ["rh-0"]
    mock_suppress.assert_called_once_with("bad@co.test", reason="BOUNCE")

    log_path = SesEventLogEntry.get_index_dir("test-campaign") / "log.usv"
    entries = [SesEventLogEntry.from_usv(line) for line in log_path.read_text().splitlines() if line]
    assert len(entries) == 1
    assert entries[0].event_type == "BOUNCE"
    assert entries[0].message_id == "msg-1"
    assert entries[0].sub_type == "Permanent"

    from cocli.core.exclusions import ExclusionManager

    ex_mgr = ExclusionManager("test-campaign")
    assert ex_mgr.is_excluded(domain="bad@co.test")
    exc = ex_mgr.get_exclusion(domain="bad@co.test")
    assert exc is not None and exc.reason == "unsubscribe:BOUNCE"


def test_transient_bounce_is_recorded_but_not_suppressed(mock_cocli_env, mocker) -> None:
    mock_suppress = mocker.patch(
        "cocli.application.ses_suppression_service.SesSuppressionService.suppress_email"
    )
    sqs = FakeSqs([_sns_envelope(_bounce_event("msg-2", "soft@co.test", bounce_type="Transient"))])

    service = EmailEventsService("test-campaign", region="us-west-1", sqs_client=sqs)
    result = service.poll(limit=10)

    assert result.recorded == 1
    assert result.suppressed == []
    mock_suppress.assert_not_called()

    from cocli.core.exclusions import ExclusionManager

    assert not ExclusionManager("test-campaign").is_excluded(domain="soft@co.test")


def test_complaint_is_always_suppressed(mock_cocli_env, mocker) -> None:
    mock_suppress = mocker.patch(
        "cocli.application.ses_suppression_service.SesSuppressionService.suppress_email",
        return_value=True,
    )
    sqs = FakeSqs([_sns_envelope(_complaint_event("msg-3", "angry@co.test"))])

    service = EmailEventsService("test-campaign", region="us-west-1", sqs_client=sqs)
    result = service.poll(limit=10)

    assert result.recorded == 1
    assert result.suppressed == ["angry@co.test"]
    mock_suppress.assert_called_once_with("angry@co.test", reason="COMPLAINT")

    log_path = SesEventLogEntry.get_index_dir("test-campaign") / "log.usv"
    entries = [SesEventLogEntry.from_usv(line) for line in log_path.read_text().splitlines() if line]
    assert entries[0].event_type == "COMPLAINT"
    assert entries[0].sub_type == "abuse"


def test_non_bounce_complaint_events_are_ignored_and_still_deleted(mock_cocli_env, mocker) -> None:
    sqs = FakeSqs(
        [_sns_envelope({"eventType": "Delivery", "mail": {"messageId": "msg-4", "destination": ["x@co.test"]}})]
    )
    service = EmailEventsService("test-campaign", region="us-west-1", sqs_client=sqs)
    result = service.poll(limit=10)

    assert result.fetched == 1
    assert result.recorded == 0
    assert result.ignored == 1
    assert sqs.deleted == ["rh-0"]

    log_path = SesEventLogEntry.get_index_dir("test-campaign") / "log.usv"
    assert not log_path.exists()


def test_unparseable_message_is_ignored_and_deleted_not_left_stuck(mock_cocli_env) -> None:
    sqs = FakeSqs(["not json"])
    service = EmailEventsService("test-campaign", region="us-west-1", sqs_client=sqs)
    result = service.poll(limit=10)

    assert result.ignored == 1
    assert result.recorded == 0
    assert sqs.deleted == ["rh-0"]


def test_already_excluded_recipient_is_not_re_added(mock_cocli_env, mocker) -> None:
    mocker.patch(
        "cocli.application.ses_suppression_service.SesSuppressionService.suppress_email",
        return_value=True,
    )
    from cocli.core.exclusions import ExclusionManager

    ExclusionManager("test-campaign").add_exclusion(domain="repeat@co.test", reason="unsubscribe:COMPLAINT")

    sqs = FakeSqs([_sns_envelope(_complaint_event("msg-5", "repeat@co.test"))])
    service = EmailEventsService("test-campaign", region="us-west-1", sqs_client=sqs)
    service.poll(limit=10)

    exc = ExclusionManager("test-campaign").get_exclusion(domain="repeat@co.test")
    assert exc is not None and exc.reason == "unsubscribe:COMPLAINT"
