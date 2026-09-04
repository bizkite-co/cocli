import aws_cdk as cdk
import aws_cdk.assertions as assertions

from cdk_scraper_deployment.email_stack import CocliEmailStack


def test_email_stack_records_ses_identity() -> None:
    app = cdk.App()
    stack = CocliEmailStack(
        app,
        "TestEmail",
        campaign_name="roadmap",
        sending_domain="getretirementtaxanalyzer.com",
        mail_from_domain="bounce.getretirementtaxanalyzer.com",
        configuration_set_name="prs-default",
        env=cdk.Environment(account="865664998993", region="us-west-1"),
    )
    template = assertions.Template.from_stack(stack)
    template.resource_count_is("AWS::SES::EmailIdentity", 1)
    template.resource_count_is("AWS::SES::ConfigurationSet", 1)
    template.has_resource_properties(
        "AWS::SES::EmailIdentity",
        {
            "EmailIdentity": "getretirementtaxanalyzer.com",
            "MailFromAttributes": {
                "MailFromDomain": "bounce.getretirementtaxanalyzer.com",
                "BehaviorOnMxFailure": "USE_DEFAULT_VALUE",
            },
        },
    )
