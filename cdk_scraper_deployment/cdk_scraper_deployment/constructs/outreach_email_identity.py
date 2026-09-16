"""A self-contained SES sending identity + config set + event
destinations, as a reusable Construct rather than a whole Stack - so it
can be composed, tested, and reasoned about independently of whichever
Stack hosts it.

Always creates its own resources from scratch (own SNS topic included) -
it is deliberately NOT a general-purpose "reconcile with whatever already
exists" tool. A campaign's pre-existing, out-of-band email infrastructure
(e.g. a product's own transactional mail, unrelated to cocli's outbound
sales) is never a target for this construct; see the
`trimcleanup-ses-and-other-resources-in-the-westmonroe-support-pg-it-shared-aws-account`
task-agent ticket for that separate cleanup effort. This is a *create
recipe*: deploy, then add the DKIM CNAME / bounce MX outputs at the
domain's actual DNS host (GoDaddy for getretirementtaxanalyzer.com, not
Route53 - this construct does not manage either).
"""

from __future__ import annotations

from typing import Any

import aws_cdk as cdk
from aws_cdk import aws_ses as ses
from aws_cdk import aws_sns as sns
from constructs import Construct

# Matches what's live on the legacy prs-default config set (verified via
# `aws sesv2 get-configuration-set-event-destinations`, 2026-09-16) - kept
# identical here so a future decision to standardize on one event-type
# list doesn't need to guess what "the right list" was.
ALL_SES_EVENT_TYPES = [
    "SEND",
    "REJECT",
    "BOUNCE",
    "COMPLAINT",
    "DELIVERY",
    "OPEN",
    "CLICK",
    "RENDERING_FAILURE",
    "DELIVERY_DELAY",
    "SUBSCRIPTION",
]


class CocliOutreachEmailIdentity(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        campaign_name: str,
        sending_domain: str,
        mail_from_domain: str,
        configuration_set_name: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.config_set = ses.CfnConfigurationSet(
            self,
            "ConfigurationSet",
            name=configuration_set_name,
            sending_options=ses.CfnConfigurationSet.SendingOptionsProperty(
                sending_enabled=True
            ),
            reputation_options=ses.CfnConfigurationSet.ReputationOptionsProperty(
                reputation_metrics_enabled=True
            ),
        )
        self.config_set.apply_removal_policy(cdk.RemovalPolicy.RETAIN)

        self.identity = ses.CfnEmailIdentity(
            self,
            "SendingDomain",
            email_identity=sending_domain,
            configuration_set_attributes=ses.CfnEmailIdentity.ConfigurationSetAttributesProperty(
                configuration_set_name=configuration_set_name
            ),
            dkim_attributes=ses.CfnEmailIdentity.DkimAttributesProperty(
                signing_enabled=True
            ),
            mail_from_attributes=ses.CfnEmailIdentity.MailFromAttributesProperty(
                mail_from_domain=mail_from_domain,
                behavior_on_mx_failure="USE_DEFAULT_VALUE",
            ),
            feedback_attributes=ses.CfnEmailIdentity.FeedbackAttributesProperty(
                email_forwarding_enabled=True
            ),
        )
        self.identity.add_dependency(self.config_set)
        self.identity.apply_removal_policy(cdk.RemovalPolicy.RETAIN)

        self.events_topic = sns.Topic(
            self, "EmailEventsTopic", topic_name=f"{campaign_name}-cocli-outreach-events"
        )

        self._add_event_destination(
            "SendLogEventDestination",
            configuration_set_name,
            name="cocli-outreach-send-log",
            cloud_watch_dimensions=[("tag", "MESSAGE_TAG", "message"), ("header", "EMAIL_HEADER", "header")],
        )
        self._add_event_destination(
            "DetailedLogsEventDestination",
            configuration_set_name,
            name="cocli-outreach-detailed-logs",
            cloud_watch_dimensions=[
                ("tag", "MESSAGE_TAG", "default-tag"),
                ("header", "EMAIL_HEADER", "default-header"),
                ("link", "LINK_TAG", "default-link"),
            ],
        )
        sns_destination = ses.CfnConfigurationSetEventDestination(
            self,
            "SnsEventDestination",
            configuration_set_name=configuration_set_name,
            event_destination=ses.CfnConfigurationSetEventDestination.EventDestinationProperty(
                name="cocli-outreach-to-sns",
                enabled=True,
                matching_event_types=ALL_SES_EVENT_TYPES,
                sns_destination=ses.CfnConfigurationSetEventDestination.SnsDestinationProperty(
                    topic_arn=self.events_topic.topic_arn,
                ),
            ),
        )
        sns_destination.add_dependency(self.config_set)

        self.sending_domain = sending_domain
        self.mail_from_domain = mail_from_domain
        self.configuration_set_name = configuration_set_name
        self.campaign_name = campaign_name
        self.bounce_mx = f"feedback-smtp.{cdk.Stack.of(self).region}.amazonses.com"
        # CfnOutputs are deliberately NOT defined here - a CfnOutput's
        # logical id gets prefixed+hashed by CDK when it lives inside a
        # child construct instead of directly on the Stack (e.g.
        # "SendingDomainName" becomes "IdentitySendingDomainNameF2A0422A"),
        # which would break the clean, stable names the DNS-handoff
        # docstring promises. The hosting Stack (email_stack.py) defines
        # them, reading these public attributes.

    def _add_event_destination(
        self,
        construct_id: str,
        configuration_set_name: str,
        *,
        name: str,
        cloud_watch_dimensions: list[tuple[str, str, str]],
    ) -> None:
        destination = ses.CfnConfigurationSetEventDestination(
            self,
            construct_id,
            configuration_set_name=configuration_set_name,
            event_destination=ses.CfnConfigurationSetEventDestination.EventDestinationProperty(
                name=name,
                enabled=True,
                matching_event_types=ALL_SES_EVENT_TYPES,
                cloud_watch_destination=ses.CfnConfigurationSetEventDestination.CloudWatchDestinationProperty(
                    dimension_configurations=[
                        ses.CfnConfigurationSetEventDestination.DimensionConfigurationProperty(
                            dimension_name=dim_name,
                            dimension_value_source=dim_source,
                            default_dimension_value=default_value,
                        )
                        for dim_name, dim_source, default_value in cloud_watch_dimensions
                    ]
                ),
            ),
        )
        destination.add_dependency(self.config_set)
