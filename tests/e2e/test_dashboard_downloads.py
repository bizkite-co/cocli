import pytest
from playwright.async_api import expect


@pytest.fixture(scope="session")
def turboship_config():
    from cocli.core.config import load_campaign_config
    return load_campaign_config("turboship")


@pytest.fixture(scope="session")
def turboship_auth_creds(turboship_config, request):
    aws_config = turboship_config.get("aws", {})
    username_path = aws_config.get("cocli_op_test_username")
    password_path = aws_config.get("cocli_op_test_password")

    if not username_path or not password_path:
        pytest.skip("OP test credentials paths not found in turboship config.")

    get_op_secret = request.getfixturevalue("_get_op_secret")
    username = get_op_secret(username_path)
    password = get_op_secret(password_path)
    return {"username": username, "password": password}


@pytest.fixture(scope="session")
def _get_op_secret():
    def _fn(op_path: str) -> str:
        from cocli.application.services import ServiceContainer
        services = ServiceContainer()
        secret = services.secret_service.get_secret(op_path)
        if not secret:
            raise Exception(f"Failed to read secret from 1Password: {op_path}")
        return secret
    return _fn


@pytest.mark.asyncio
async def test_dashboard_download_links_populate_after_login(page, turboship_auth_creds, visible_locator):
    """
    Regression test for the download CSV/JSON buttons: on a fresh session
    (no stored Cognito token) the dashboard must complete login and then
    rewrite the '#' placeholder hrefs to real, downloadable export URLs with
    a `download` attribute - not leave them as dead links.
    """
    dashboard_url = "https://cocli.turboheat.net/index.html"

    await page.goto(dashboard_url)

    # A session with no token must be redirected to Cognito login, not left
    # on the dashboard with unpopulated links.
    await page.wait_for_url("**/login**", timeout=15000)

    user_field = await visible_locator(page, 'input[name="username"]')
    pass_field = await visible_locator(page, 'input[name="password"]')
    submit_btn = await visible_locator(page, 'input[name="signInSubmitButton"], button[name="signInSubmitButton"]')

    await user_field.fill(turboship_auth_creds["username"])
    await pass_field.fill(turboship_auth_creds["password"])
    await submit_btn.click()

    await page.wait_for_url(f"{dashboard_url}*", timeout=30000)

    download_link = page.locator("#download-link")
    download_link_json = page.locator("#download-link-json")

    # The report fetch is async - give it a real chance to populate the
    # hrefs before asserting, rather than racing it.
    await expect(download_link).not_to_have_attribute("href", "#", timeout=15000)
    await expect(download_link).to_have_attribute("download", "turboship-emails.csv")
    await expect(download_link_json).to_have_attribute("download", "turboship-emails.json")

    href = await download_link.get_attribute("href")
    assert href is not None and "/exports/turboship-emails.csv" in href

    async with page.expect_download() as download_info:
        await download_link.click()
    download = await download_info.value
    assert download.suggested_filename == "turboship-emails.csv"
