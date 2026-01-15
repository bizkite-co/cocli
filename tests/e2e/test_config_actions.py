import pytest
import asyncio
import json
import boto3
from playwright.async_api import expect

@pytest.mark.asyncio
async def test_add_exclusion_bridge(page, auth_creds, campaign_config, visible_locator):
    """Verifies that adding an exclusion in the UI correctly reaches the AWS SQS queue."""
    dashboard_url = "https://cocli.retirementtaxanalyzer.com/index.html"
    config_url = "https://cocli.retirementtaxanalyzer.com/config/index.html"

    # 1. Login (Reuse login logic)
    await page.goto(dashboard_url)
    if "login" in page.url:
        user_field = await visible_locator(page, 'input[name="username"]')
        pass_field = await visible_locator(page, 'input[name="password"]')
        submit_btn = await visible_locator(page, 'input[name="signInSubmitButton"], button[name="signInSubmitButton"]')
        await user_field.fill(auth_creds["username"])
        await pass_field.fill(auth_creds["password"])
        await submit_btn.click()
        await page.wait_for_url(f"{dashboard_url}*", timeout=30000)

    # 2. Go to Config
    await page.goto(config_url)
    await expect(page.locator("h3:has-text('Excluded Companies')")).to_be_visible()

    # 3. Add test exclusion
    test_slug = f"e2e-bridge-test-{int(asyncio.get_event_loop().time())}.com"
    print(f"Adding test exclusion: {test_slug}")
    await page.fill("#new-exclude", test_slug)
    await page.click("button:has-text('Add')")

    # Verify visual feedback appears in the list (this works even on the old UI)
    await expect(page.locator("#exclusions-list")).to_contain_text(test_slug)
    await expect(page.locator("#exclusions-list")).to_contain_text("Pending addition")

    # 4. Submit to SQS
    await page.click("button.btn-submit")
    await expect(page.locator("#submission-status")).to_contain_text("Successfully submitted", timeout=15000)

    # 5. Verify SQS bridge
    aws_config = campaign_config.get("aws", {})
    queue_url = aws_config.get("cocli_command_queue_url")

    print(f"Verifying SQS bridge at {queue_url}")
    session = boto3.Session(profile_name=aws_config.get("profile") or aws_config.get("aws_profile"))
    sqs = session.client("sqs", region_name=aws_config.get("region", "us-east-1"))

    # Check queue stats first
    attrs = sqs.get_queue_attributes(
        QueueUrl=queue_url,
        AttributeNames=['ApproximateNumberOfMessages', 'ApproximateNumberOfMessagesNotVisible']
    ).get('Attributes', {})
    print(f"Initial SQS Stats: {attrs}")

    found = False
    for i in range(10): # Increase to 10 attempts
        print(f"Polling SQS attempt {i+1}...")
        response = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=2,
            AttributeNames=['SentTimestamp']
        )

        messages = response.get("Messages", [])
        print(f"Found {len(messages)} messages in this batch.")

        for msg in messages:
            body_str = msg["Body"]
            try:
                body = json.loads(body_str)
                cmd_text = body.get("command", "")
                print(f"  - Message: {cmd_text}")
                if test_slug in cmd_text:
                    found = True
                    print(f"SUCCESS: Found matching command for {test_slug}")
                    break
            except Exception as e:
                print(f"  - Failed to parse message body: {e}")

        if found:
            break
        await asyncio.sleep(1)

    if not found:
        # Check stats again
        attrs_final = sqs.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=['ApproximateNumberOfMessages', 'ApproximateNumberOfMessagesNotVisible']
        ).get('Attributes', {})
        print(f"Final SQS Stats: {attrs_final}")

    assert found, f"Command for {test_slug} did not reach SQS queue {queue_url}. Check if a worker processed it already."