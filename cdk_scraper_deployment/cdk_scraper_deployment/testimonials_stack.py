"""Testimonials/feedback intake for a campaign's outreach landing page.

Replaces formsubmit.co (confirmed unreliable: HTTP 500 on every request,
before and after account activation, with a broken activation flow and no
account/dashboard to review - see cocli conversation 2026-09-29). Gives
the campaign a durable, self-owned store using the SAME S3 queue
convention every other cocli queue already uses (docs/data-management/
directory-data-structure.md: campaigns/<name>/queues/<queue>/pending/ +
completed/, task.json per item) - no database. A first version of this
used DynamoDB; that was wrong for a data-centric app that stores
everything as sharded USV/JSON in S3, and was torn down.

The Lambda writes one JSON file per submission straight into the
campaign's existing S3 data bucket, at
campaigns/<campaign>/queues/testimonials/pending/<uuid>.json - structurally
identical to how gm-details tasks land in queues/gm-details/pending/.
cocli's own smart-sync pulls it down; a new cocli command processes
pending/ into the engagement log + a company note, then moves the file to
completed/<uuid>.json as the witness receipt, exactly like gm-details.
"""

from __future__ import annotations

from typing import Any

import aws_cdk as cdk
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from constructs import Construct

_HANDLER_CODE = '''
import json
import logging
import os
import time
import uuid

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client("s3")
BUCKET_NAME = os.environ["BUCKET_NAME"]
QUEUE_PREFIX = os.environ["QUEUE_PREFIX"]

FIELDS = (
    "name", "firm", "email", "message", "permission_to_quote",
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
    "page_url",
)


def handler(event, context):
    # Logged unconditionally, before the S3 write, so the captured data is
    # visible in CloudWatch (14-day retention - see app.py's
    # LogRetentionAspect) even if the S3 write itself fails. This is a
    # second, independent recovery path alongside the S3 queue item
    # itself, not a replacement for it - S3 is still the primary record
    # cocli processes.
    task_id = str(uuid.uuid4())
    try:
        body = json.loads(event.get("body") or "{}")
    except Exception as exc:
        logger.error("testimonial_submission_parse_failed id=%s raw_body=%r error=%s", task_id, event.get("body"), exc)
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"success": False, "error": "Could not parse request body"}),
        }

    item = {"id": task_id, "received_at": int(time.time())}
    for field in FIELDS:
        item[field] = str(body.get(field, ""))

    logger.info("testimonial_submission_received %s", json.dumps(item))

    try:
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=f"{QUEUE_PREFIX}{task_id}.json",
            Body=json.dumps(item).encode("utf-8"),
            ContentType="application/json",
        )
        logger.info("testimonial_submission_stored id=%s key=%s%s.json", task_id, QUEUE_PREFIX, task_id)
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"success": True}),
        }
    except Exception as exc:  # noqa: BLE001 - always return JSON, never a raw 500 HTML page
        # The full submission was already logged above, so even an S3
        # failure here doesn't lose the data - it's recoverable from
        # CloudWatch by searching for this task_id within the retention
        # window.
        logger.error("testimonial_submission_s3_write_failed id=%s error=%s", task_id, exc)
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"success": False, "error": str(exc)}),
        }
'''


class CocliTestimonialsStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        campaign_name: str,
        data_bucket_name: str,
        allowed_origin: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        queue_prefix = f"campaigns/{campaign_name}/queues/testimonials/pending/"
        data_bucket = s3.Bucket.from_bucket_name(self, "DataBucket", data_bucket_name)

        # Explicit LogGroup (rather than letting the Lambda service
        # auto-create one at first invocation with "Never expire"
        # retention) so LogRetentionAspect in app.py has something to
        # visit and set to 14 days - the captured-submission logging
        # below is a secondary recovery path, so it needs a bounded but
        # real retention window, not "forever" or "whatever the account
        # default happens to be."
        log_group = logs.LogGroup(self, "IntakeFunctionLogGroup")

        self.fn = lambda_.Function(
            self,
            "IntakeFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=lambda_.Code.from_inline(_HANDLER_CODE),
            environment={
                "BUCKET_NAME": data_bucket_name,
                "QUEUE_PREFIX": queue_prefix,
            },
            timeout=cdk.Duration.seconds(10),
            log_group=log_group,
        )
        # Scoped to exactly this queue's pending/ prefix - the Lambda must
        # never be able to write anywhere else in the campaign's data.
        self.fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:PutObject"],
                resources=[data_bucket.arn_for_objects(f"{queue_prefix}*")],
            )
        )

        self.fn_url = self.fn.add_function_url(
            auth_type=lambda_.FunctionUrlAuthType.NONE,
            cors=lambda_.FunctionUrlCorsOptions(
                allowed_origins=[allowed_origin],
                allowed_methods=[lambda_.HttpMethod.POST],
                allowed_headers=["content-type"],
            ),
        )

        cdk.CfnOutput(self, "QueuePrefix", value=f"s3://{data_bucket_name}/{queue_prefix}")
        cdk.CfnOutput(self, "IntakeFunctionUrl", value=self.fn_url.url)
