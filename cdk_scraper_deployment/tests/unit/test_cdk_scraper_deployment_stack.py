import aws_cdk as core
import aws_cdk.assertions as assertions

from cdk_scraper_deployment.cdk_scraper_deployment_stack import CdkScraperDeploymentStack

# example tests. To run these tests, uncomment this file along with the example
# resource in cdk_scraper_deployment/cdk_scraper_deployment_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = CdkScraperDeploymentStack(app, "cdk-scraper-deployment")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
