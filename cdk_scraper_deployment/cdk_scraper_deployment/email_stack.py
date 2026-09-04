"""SES sending identity for a campaign (separate region from the scraper stack).

This is a *create recipe* for the next client: deploy, then add the DKIM
CNAME / bounce MX outputs at their DNS host. It does not manage GoDaddy
or Route53. Do not `cdk deploy` over an identity that already exists with
manually-issued Easy DKIM tokens unless you intend to rotate those CNAMEs.
"""

from __future__ import annotations

from typing import Any

import aws_cdk as cdk
from aws_cdk import aws_ses as ses
from constructs import Construct


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

        config_set = ses.CfnConfigurationSet(
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
        config_set.apply_removal_policy(cdk.RemovalPolicy.RETAIN)

        identity = ses.CfnEmailIdentity(
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
        identity.add_dependency(config_set)
        identity.apply_removal_policy(cdk.RemovalPolicy.RETAIN)

        bounce_mx = f"feedback-smtp.{self.region}.amazonses.com"
        cdk.CfnOutput(self, "SendingDomainName", value=sending_domain)
        cdk.CfnOutput(self, "MailFromDomain", value=mail_from_domain)
        cdk.CfnOutput(self, "MailFromMx", value=bounce_mx)
        cdk.CfnOutput(self, "ConfigurationSetName", value=configuration_set_name)
        cdk.CfnOutput(self, "CampaignName", value=campaign_name)
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
