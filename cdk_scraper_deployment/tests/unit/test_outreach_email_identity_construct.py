"""CocliOutreachEmailIdentity tested on its own, independent of which
Stack hosts it - the point of decomposing it out of CocliEmailStack."""

import aws_cdk as cdk
import aws_cdk.assertions as assertions

from cdk_scraper_deployment.constructs.outreach_email_identity import (
    CocliOutreachEmailIdentity,
)


def _build_stack() -> cdk.Stack:
    app = cdk.App()
    stack = cdk.Stack(app, "HostStack", env=cdk.Environment(account="111111111111", region="us-west-1"))
    CocliOutreachEmailIdentity(
        stack,
        "Identity",
        campaign_name="acme",
        sending_domain="outreach.acme.test",
        mail_from_domain="bounce.outreach.acme.test",
        configuration_set_name="cocli-outreach-acme",
    )
    return stack


def test_construct_creates_identity_config_set_topic_and_three_destinations() -> None:
    template = assertions.Template.from_stack(_build_stack())
    template.resource_count_is("AWS::SES::EmailIdentity", 1)
    template.resource_count_is("AWS::SES::ConfigurationSet", 1)
    template.resource_count_is("AWS::SNS::Topic", 1)
    template.resource_count_is("AWS::SES::ConfigurationSetEventDestination", 3)


def test_construct_exposes_resources_for_the_hosting_stack_to_read() -> None:
    """CfnOutputs live on the hosting Stack (email_stack.py), not here -
    see the comment in outreach_email_identity.py for why (logical-id
    prefixing). This construct just needs to expose what a Stack needs."""
    app = cdk.App()
    stack = cdk.Stack(app, "HostStack", env=cdk.Environment(account="111111111111", region="us-west-1"))
    identity = CocliOutreachEmailIdentity(
        stack,
        "Identity",
        campaign_name="acme",
        sending_domain="outreach.acme.test",
        mail_from_domain="bounce.outreach.acme.test",
        configuration_set_name="cocli-outreach-acme",
    )
    assert identity.sending_domain == "outreach.acme.test"
    assert identity.mail_from_domain == "bounce.outreach.acme.test"
    assert identity.configuration_set_name == "cocli-outreach-acme"
    assert identity.campaign_name == "acme"
    assert identity.bounce_mx == "feedback-smtp.us-west-1.amazonses.com"
    assert identity.events_topic.topic_arn is not None
    assert identity.identity.attr_dkim_dns_token_name1 is not None


def test_construct_event_destinations_use_cocli_branded_names() -> None:
    template = assertions.Template.from_stack(_build_stack())
    names = {
        r["Properties"]["EventDestination"]["Name"]
        for r in template.to_json()["Resources"].values()
        if r["Type"] == "AWS::SES::ConfigurationSetEventDestination"
    }
    assert names == {"cocli-outreach-send-log", "cocli-outreach-detailed-logs", "cocli-outreach-to-sns"}
