import asyncio
from playwright.async_api import async_playwright
from pathlib import Path

async def capture_ground_truth() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        # Ground Truth URL provided by user
        url = "https://www.google.com/maps/search/auto+parts/@34.2499124,-118.2605756,2882m/data=!3m1!1e3?hl=en-US"
        print(f"Navigating to {url}...")
        
        try:
            await page.goto(url, wait_until="load", timeout=60000)
            # Wait for results to hydrate
            await page.wait_for_selector('div[role="article"]', timeout=30000)
            # Wait for semantic ARIA labels (Stars/Reviews)
            await page.locator('span[aria-label*="stars"]').first.wait_for(timeout=10000)
            await asyncio.sleep(2) # Final buffer
            
            listings = await page.locator('div[role="article"]').all()
            print(f"Found {len(listings)} listings on first page.")
            
            output_dir = Path("tests/data/ground_truth/autoparts")
            output_dir.mkdir(parents=True, exist_ok=True)
            
            for i, listing in enumerate(listings):
                html = await listing.evaluate("el => el.outerHTML")
                # We'll use a simple name if we can find it
                name_el = await listing.locator('div.qBF1Pd').first.all_inner_texts()
                name = name_el[0] if name_el else f"item_{i}"
                filename = f"{i:02d}_{name.replace(' ', '_').replace('/', '_')}.html"
                
                with open(output_dir / filename, "w", encoding="utf-8") as f:
                    f.write(html)
                print(f"  Saved: {filename}")
                
        except Exception as e:
            print(f"Capture failed: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(capture_ground_truth())
