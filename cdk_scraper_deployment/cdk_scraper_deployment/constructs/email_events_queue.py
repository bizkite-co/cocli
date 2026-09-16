"""SQS queue subscribed to a campaign's outbound-sales SES events SNS
topic - the missing link that left events "published into the void"
(CocliOutreachEmailIdentity creates the topic; nothing consumed it until
this construct). Kept separate from CocliOutreachEmailIdentity - queue
consumption is a distinct concern from identity/config-set creation, and
this only needs the topic's ARN, not the identity itself.

Uses the SNS-wrapped delivery format (not raw_message_delivery), which
EmailEventsService.poll() (cocli/application/email_events_service.py)
expects when unwrapping the SES event JSON from the SNS envelope.
"""

from __future__ import annotations

from typing import Any

import aws_cdk as cdk
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as sns_subs
from aws_cdk import aws_sqs as sqs
from constructs import Construct


class CocliEmailEventsQueue(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        campaign_name: str,
        events_topic: sns.ITopic,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Same deterministic name EmailEventsService._queue_url() looks
        # up by - no queue URL needs to be synced into config.toml.
        self.queue = sqs.Queue(
            self,
            "Queue",
            queue_name=f"{campaign_name}-cocli-outreach-events",
            retention_period=cdk.Duration.days(4),
        )
        events_topic.add_subscription(sns_subs.SqsSubscription(self.queue))
