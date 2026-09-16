"""Ingests SES bounce/complaint events from the SQS queue subscribed to
a campaign's outbound-sales SNS topic (cdk CocliEmailEventsQueue - see
cdk_scraper_deployment/cdk_scraper_deployment/constructs/email_events_queue.py).
Mirrors EmailService.poll()'s IMAP-polling shape, applied to SQS instead:
read, record, act, delete.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class PollEventsResult:
    fetched: int = 0
    recorded: int = 0
    ignored: int = 0
    suppressed: list[str] = field(default_factory=list)


class EmailEventsService:
    def __init__(
        self,
        campaign_name: str,
        region: str,
        profile: Optional[str] = None,
        sqs_client: Optional[Any] = None,
    ) -> None:
        self.campaign_name = campaign_name
        self.region = region
        self._profile = profile
        self._sqs = sqs_client

    def _client(self) -> Any:
        if self._sqs is None:
            from cocli.core.reporting import get_boto3_session

            session = get_boto3_session({}, profile_name=self._profile)
            self._sqs = session.client("sqs", region_name=self.region)
        return self._sqs

    def _queue_url(self) -> str:
        client = self._client()
        # Deterministic from campaign_name (CocliEmailEventsQueue names it
        # this exactly) - no need to persist/sync a queue URL into
        # config.toml, SQS's own name->URL lookup is enough.
        queue_name = f"{self.campaign_name}-cocli-outreach-events"
        resp = client.get_queue_url(QueueName=queue_name)
        return str(resp["QueueUrl"])

    def poll(self, *, limit: int = 10) -> PollEventsResult:
        from cocli.application.ses_suppression_service import SesSuppressionService
        from cocli.core.exclusions import ExclusionManager
        from cocli.models.campaigns.indexes.ses_event_log import SesEventLogEntry

        result = PollEventsResult()
        client = self._client()
        queue_url = self._queue_url()

        resp = client.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=min(limit, 10),
            WaitTimeSeconds=1,
        )
        messages = resp.get("Messages", [])
        result.fetched = len(messages)

        ex_mgr = ExclusionManager(self.campaign_name)
        ses_suppress = SesSuppressionService(region=self.region, profile=self._profile)
        entries: list[SesEventLogEntry] = []

        for msg in messages:
            receipt_handle = msg["ReceiptHandle"]
            entry = self._parse_event(msg, result)
            if entry is not None:
                entries.append(entry)
                if entry.event_type == "COMPLAINT" or entry.sub_type == "Permanent":
                    self._suppress(entry.recipient, entry.event_type, ex_mgr, ses_suppress, result)
            client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)

        if entries:
            index_dir = SesEventLogEntry.get_index_dir(self.campaign_name)
            index_dir.mkdir(parents=True, exist_ok=True)
            log_path = index_dir / "log.usv"
            with open(log_path, "a", encoding="utf-8") as f:
                for entry in entries:
                    f.write(entry.to_usv())
            SesEventLogEntry.save_datapackage(index_dir, "ses_event_log", "log.usv")

        return result

    def _parse_event(self, msg: dict[str, Any], result: PollEventsResult) -> Optional[Any]:
        from cocli.models.campaigns.indexes.ses_event_log import SesEventLogEntry

        try:
            envelope = json.loads(msg["Body"])
            if envelope.get("Type") != "Notification":
                result.ignored += 1
                return None
            event = json.loads(envelope["Message"])
        except Exception as exc:
            logger.warning("email_events poll: could not parse message body: %s", exc)
            result.ignored += 1
            return None

        event_type = event.get("eventType")
        if event_type not in ("Bounce", "Complaint"):
            result.ignored += 1
            return None

        mail = event.get("mail") or {}
        message_id = str(mail.get("messageId") or "")
        destinations = mail.get("destination") or []
        recipient = str(destinations[0]) if destinations else ""

        if event_type == "Bounce":
            bounce = event.get("bounce") or {}
            sub_type = str(bounce.get("bounceType") or "") or None
            mapped_type: Any = "BOUNCE"
        else:
            complaint = event.get("complaint") or {}
            sub_type = str(complaint.get("complaintFeedbackType") or "") or None
            mapped_type = "COMPLAINT"

        result.recorded += 1
        return SesEventLogEntry(
            event_type=mapped_type,
            message_id=message_id,
            recipient=recipient,
            sub_type=sub_type,
        )

    def _suppress(
        self,
        recipient: str,
        event_type: str,
        ex_mgr: Any,
        ses_suppress: Any,
        result: PollEventsResult,
    ) -> None:
        if not recipient:
            return
        # Matches `cocli email unsubscribe`'s own reason format exactly
        # (commands/email.py) so auto-suppressed bounces/complaints show
        # up in the existing compute_unsubscribe_rate() metric too, not a
        # separate parallel taxonomy.
        if not ex_mgr.is_excluded(domain=recipient):
            ex_mgr.add_exclusion(domain=recipient, reason=f"unsubscribe:{event_type}")
        try:
            ses_suppress.suppress_email(recipient, reason=event_type)
        except Exception as exc:
            logger.warning("email_events poll: SES suppression failed for %s: %s", recipient, exc)
        result.suppressed.append(recipient)
