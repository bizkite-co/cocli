import asyncio
import sys
from playwright.async_api import async_playwright

async def test():
    print("Starting Playwright sanity check...")
    async with async_playwright() as p:
        try:
            print("Launching browser...")
            browser = await p.chromium.launch(headless=True)
            print("Creating page...")
            page = await browser.new_page()
            print("Navigating to example.com...")
            await page.goto('https://example.com')
            title = await page.title()
            print(f"Page title: {title}")
            if "Example Domain" in title:
                print("SUCCESS: Browser launched and navigated inside container")
            else:
                print(f"FAILURE: Unexpected title: {title}")
                sys.exit(1)
            await browser.close()
        except Exception as e:
            print(f"FAILURE: {e}")
            sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test())
