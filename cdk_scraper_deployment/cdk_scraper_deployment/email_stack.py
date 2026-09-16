"""Thin Stack wrapper around CocliOutreachEmailIdentity (see
constructs/outreach_email_identity.py for the actual resources) - kept as
its own Stack, separate from CdkScraperDeploymentStack, so a campaign's
outbound-sales email identity can be deployed/torn down independently of
its scraper infrastructure.
"""

from __future__ import annotations

from typing import Any

import aws_cdk as cdk
from constructs import Construct

from .constructs.email_events_queue import CocliEmailEventsQueue
from .constructs.outreach_email_identity import CocliOutreachEmailIdentity


class CocliEmailStack(cdk.Stack):
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

        self.identity = CocliOutreachEmailIdentity(
            self,
            "OutreachEmailIdentity",
            campaign_name=campaign_name,
            sending_domain=sending_domain,
            mail_from_domain=mail_from_domain,
            configuration_set_name=configuration_set_name,
        )

        self.events_queue = CocliEmailEventsQueue(
            self,
            "EventsQueue",
            campaign_name=campaign_name,
            events_topic=self.identity.events_topic,
        )

        identity = self.identity.identity
        cdk.CfnOutput(self, "SendingDomainName", value=self.identity.sending_domain)
        cdk.CfnOutput(self, "MailFromDomain", value=self.identity.mail_from_domain)
        cdk.CfnOutput(self, "MailFromMx", value=self.identity.bounce_mx)
        cdk.CfnOutput(self, "ConfigurationSetName", value=self.identity.configuration_set_name)
        cdk.CfnOutput(self, "CampaignName", value=self.identity.campaign_name)
        cdk.CfnOutput(self, "EmailEventsTopicArn", value=self.identity.events_topic.topic_arn)
        cdk.CfnOutput(self, "EmailEventsQueueUrl", value=self.events_queue.queue.queue_url)
        cdk.CfnOutput(self, "EmailEventsQueueArn", value=self.events_queue.queue.queue_arn)
        cdk.CfnOutput(self, "DkimCname1Name", value=identity.attr_dkim_dns_token_name1)
        cdk.CfnOutput(self, "DkimCname1Value", value=identity.attr_dkim_dns_token_value1)
        cdk.CfnOutput(self, "DkimCname2Name", value=identity.attr_dkim_dns_token_name2)
        cdk.CfnOutput(self, "DkimCname2Value", value=identity.attr_dkim_dns_token_value2)
        cdk.CfnOutput(self, "DkimCname3Name", value=identity.attr_dkim_dns_token_name3)
        cdk.CfnOutput(self, "DkimCname3Value", value=identity.attr_dkim_dns_token_value3)
        cdk.CfnOutput(
            self,
            "SpfApexHint",
            value="v=spf1 include:amazonses.com -all  (merge with existing SPF includes)",
        )
