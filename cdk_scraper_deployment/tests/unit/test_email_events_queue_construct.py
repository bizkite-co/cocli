"""CocliEmailEventsQueue: the SQS consumer that closes the "events
published into the void" gap - subscribed to an existing SNS topic
without duplicating it."""

import aws_cdk as cdk
import aws_cdk.assertions as assertions

from cdk_scraper_deployment.constructs.email_events_queue import CocliEmailEventsQueue


def test_queue_subscribes_to_the_given_topic_with_a_deterministic_name() -> None:
    app = cdk.App()
    stack = cdk.Stack(app, "HostStack", env=cdk.Environment(account="111111111111", region="us-west-1"))
    topic = cdk.aws_sns.Topic(stack, "Topic", topic_name="acme-cocli-outreach-events")

    CocliEmailEventsQueue(stack, "EventsQueue", campaign_name="acme", events_topic=topic)

    template = assertions.Template.from_stack(stack)
    template.resource_count_is("AWS::SQS::Queue", 1)
    template.resource_count_is("AWS::SNS::Subscription", 1)
    template.has_resource_properties(
        "AWS::SQS::Queue", {"QueueName": "acme-cocli-outreach-events"}
    )
    template.has_resource_properties(
        "AWS::SNS::Subscription", {"Protocol": "sqs"}
    )


def test_queue_does_not_create_a_second_topic() -> None:
    app = cdk.App()
    stack = cdk.Stack(app, "HostStack", env=cdk.Environment(account="111111111111", region="us-west-1"))
    topic = cdk.aws_sns.Topic(stack, "Topic")

    CocliEmailEventsQueue(stack, "EventsQueue", campaign_name="acme", events_topic=topic)

    template = assertions.Template.from_stack(stack)
    template.resource_count_is("AWS::SNS::Topic", 1)
