import aws_cdk as cdk
import aws_cdk.assertions as assertions

from cdk_scraper_deployment.email_stack import CocliEmailStack


def test_email_stack_records_ses_identity() -> None:
    app = cdk.App()
    stack = CocliEmailStack(
        app,
        "TestEmail",
        campaign_name="roadmap",
        sending_domain="outreach.getretirementtaxanalyzer.com",
        mail_from_domain="bounce.outreach.getretirementtaxanalyzer.com",
        configuration_set_name="cocli-outreach-roadmap",
        env=cdk.Environment(account="865664998993", region="us-west-1"),
    )
    template = assertions.Template.from_stack(stack)
    template.resource_count_is("AWS::SES::EmailIdentity", 1)
    template.resource_count_is("AWS::SES::ConfigurationSet", 1)
    template.has_resource_properties(
        "AWS::SES::EmailIdentity",
        {
            "EmailIdentity": "outreach.getretirementtaxanalyzer.com",
            "MailFromAttributes": {
                "MailFromDomain": "bounce.outreach.getretirementtaxanalyzer.com",
                "BehaviorOnMxFailure": "USE_DEFAULT_VALUE",
            },
        },
    )


def test_event_destinations_always_create_their_own_topic() -> None:
    """This construct never reconciles with pre-existing, out-of-band
    infrastructure (e.g. a product's own transactional-mail identity) -
    it always provisions its own isolated topic, for any campaign."""
    app = cdk.App()
    stack = CocliEmailStack(
        app,
        "TestEmailNewClient",
        campaign_name="next-client",
        sending_domain="outreach.example.com",
        mail_from_domain="bounce.outreach.example.com",
        configuration_set_name="cocli-outreach-next-client",
        env=cdk.Environment(account="111111111111", region="us-west-1"),
    )
    template = assertions.Template.from_stack(stack)
    template.resource_count_is("AWS::SES::ConfigurationSetEventDestination", 3)
    template.resource_count_is("AWS::SNS::Topic", 1)
    template.has_resource_properties(
        "AWS::SES::ConfigurationSetEventDestination",
        {
            "ConfigurationSetName": "cocli-outreach-next-client",
            "EventDestination": {
                "Name": "cocli-outreach-to-sns",
                "Enabled": True,
            },
        },
    )
