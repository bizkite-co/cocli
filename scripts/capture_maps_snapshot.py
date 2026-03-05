import asyncio
from playwright.async_api import async_playwright
import os

async def capture() -> None:
    async with async_playwright() as p:
        # User-agent to look more like a real browser
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        url = "https://www.google.com/maps/search/auto+parts/@34.1212138,-118.3187261,13z"
        print(f"Navigating to {url}...")
        try:
            await page.goto(url, wait_until="load", timeout=60000)
            await page.wait_for_selector('div[role="article"]', timeout=30000)
            await asyncio.sleep(5) # Final hydration
            
            listings = await page.locator('div[role="article"]').all()
            print(f"Found {len(listings)} listings.")
            
            os.makedirs("temp/canary_html", exist_ok=True)
            for i, listing in enumerate(listings[:10]):
                html = await listing.evaluate("el => el.outerHTML")
                with open(f"temp/canary_html/item_{i}.html", "w") as f:
                    f.write(html)
                print(f"Saved item_{i}.html")
        except Exception as e:
            print(f"Capture failed: {e}")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(capture())
