"""Live check that /testimonials delivers a submission into the S3 intake queue.

The unit tests only read the site source. scripts/verify_gtm_telemetry_live.py
fills the form and prints; it does not assert, and it does not look in S3.
This test submits from the live page, requires {success: true} from the
Lambda, requires the JSON to land in campaigns/roadmap/queues/testimonials/pending/,
then deletes that object.

    uv run pytest tests/e2e/test_testimonials_page.py -q

COCLI_ENV=test would point cocli's bucket helper at a -test suffix. The
Lambda writes the unsuffixed campaign bucket, so this reads
aws.data_bucket_name from the real campaign config.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

import pytest
from playwright.async_api import Page, expect

PAGE_URL = "https://getretirementtaxanalyzer.com/testimonials/"
QUEUE_PREFIX = "campaigns/roadmap/queues/testimonials/pending/"


def _s3_client(config: dict[str, Any]) -> tuple[Any, str]:
    from cocli.core.reporting import get_boto3_session, get_s3_client

    bucket = str(config.get("aws", {}).get("data_bucket_name") or "")
    if not bucket:
        pytest.fail("roadmap config has no aws.data_bucket_name")
    return get_s3_client(session=get_boto3_session(config)), bucket


def _keys_containing(s3: Any, bucket: str, token: str) -> list[str]:
    found: list[str] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=QUEUE_PREFIX):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith(".json"):
                continue
            body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
            try:
                item = json.loads(body)
            except json.JSONDecodeError:
                continue
            if token in str(item.get("message") or ""):
                found.append(key)
    return found


def _wait_for_key(s3: Any, bucket: str, token: str) -> list[str]:
    found: list[str] = []
    for _ in range(8):
        found = _keys_containing(s3, bucket, token)
        if found:
            return found
        time.sleep(1)
    return found


@pytest.mark.asyncio
async def test_live_testimonials_form_lands_in_the_s3_intake_queue(
    page: Page, load_real_campaign_config: Any
) -> None:
    token = f"E2E_TESTIMONIAL_{uuid.uuid4().hex}"
    config = load_real_campaign_config("roadmap")
    s3, bucket = _s3_client(config)
    keys: list[str] = []

    try:
        await page.goto(PAGE_URL, wait_until="domcontentloaded", timeout=30000)
        await page.fill("#feedback-name", "cocli e2e")
        await page.fill("#feedback-firm", "cocli e2e")
        await page.fill("#feedback-email", "e2e-testimonial@example.com")
        await page.fill("#feedback-message", token)

        async with page.expect_response(
            lambda response: "lambda-url" in response.url and response.request.method == "POST",
            timeout=20000,
        ) as posted:
            await page.locator("#feedback-submit-btn").click()
        response = await posted.value
        payload = await response.json()

        assert response.ok, f"intake HTTP {response.status}: {payload}"
        assert payload.get("success") is True
        await expect(page.locator("#feedback-success-msg")).to_be_visible()
        await expect(page.locator("#feedback-error-msg")).to_be_hidden()

        events = await page.evaluate(
            "() => (window.dataLayer || []).filter((entry) => entry && entry.event === 'feedback_submit')"
        )
        assert events, "feedback_submit was not pushed to dataLayer"

        keys = _wait_for_key(s3, bucket, token)
        assert keys, f"Lambda reported success but {token} is not in s3://{bucket}/{QUEUE_PREFIX}"

        stored = json.loads(s3.get_object(Bucket=bucket, Key=keys[0])["Body"].read())
        assert stored.get("name") == "cocli e2e"
        assert stored.get("email") == "e2e-testimonial@example.com"
        assert stored.get("message") == token
        assert stored.get("permission_to_quote") == "Yes"
        assert stored.get("utm_campaign") == "testimonials"
    finally:
        for key in _keys_containing(s3, bucket, token):
            s3.delete_object(Bucket=bucket, Key=key)
