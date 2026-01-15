import pytest
from playwright.async_api import expect

@pytest.mark.asyncio
async def test_dashboard_login_flow(page, auth_creds, visible_locator):
    """Verifies that the user can log in via Cognito and reach the dashboard."""
    dashboard_url = "https://cocli.retirementtaxanalyzer.com/index.html"
    
    # 1. Navigate to dashboard
    await page.goto(dashboard_url)
    
    # 2. Handle Cognito Login
    await page.wait_for_url("**/login**", timeout=15000)
    
    user_field = await visible_locator(page, 'input[name="username"]')
    pass_field = await visible_locator(page, 'input[name="password"]')
    submit_btn = await visible_locator(page, 'input[name="signInSubmitButton"], button[name="signInSubmitButton"]')

    await user_field.fill(auth_creds["username"])
    await pass_field.fill(auth_creds["password"])
    await submit_btn.click()
    
    # 3. Verify landing
    await page.wait_for_url(f"{dashboard_url}*", timeout=30000)
    await expect(page.locator("#campaign-display")).to_have_text("roadmap")