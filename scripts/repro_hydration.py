# POLICY: frictionless-data-policy-enforcement
import asyncio
import logging
import tempfile
from pathlib import Path
from playwright.async_api import async_playwright
from cocli.utils.headers import ANTI_BOT_HEADERS, USER_AGENT

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fidelity_test")

async def run_fidelity_test() -> None:
    # Target: Tax Wise Financial Services (One of your 5 examples)
    place_id = "ChIJ68K10x1dtokRXQCb6Xvmz2k"
    
    # Create a temporary profile directory
    user_data_dir = Path(tempfile.gettempdir()) / "playwright_fidelity_profile"
    user_data_dir.mkdir(parents=True, exist_ok=True)

    print("\n--- OPENING FULL-FIDELITY BROWSER ---")
    print(f"Target: {place_id}")
    print("CSS/Images: ENABLED (No more crippling)")
    print("Anti-Bot Headers: ENABLED (Your verified set)")
    
    async with async_playwright() as p:
        # Launch persistent context to simulate a real session
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=False,
            user_agent=USER_AGENT,
            extra_http_headers=ANTI_BOT_HEADERS,
            args=["--start-maximized", "--no-sandbox"],
            no_viewport=True 
        )
        
        page = context.pages[0] if context.pages else await context.new_page()
        
        # Use the URL format that redirect to the full canonical URL
        url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
        
        logger.info(f"Navigating to {url}")
        await page.goto(url, wait_until="load", timeout=60000)
        
        print("\n[INSPECTION READY]")
        print("1. Confirm the Map is fully visible.")
        print("2. Confirm the 4.8 Rating and Reviews are visible.")
        print("3. Check if the URL redirected to the long canonical format.")
        
        # Capture and Parse using our PRODUCTION modular parser
        await asyncio.to_thread(input, "\nPress ENTER here to capture HTML and parse...")

        from bs4 import BeautifulSoup
        from cocli.scrapers.google_maps_parsers.extract_rating_reviews import extract_rating_reviews
        
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")
        # Pass full HTML text for the proximity scan
        results = extract_rating_reviews(soup, soup.get_text(), debug=True)
        
        print(f"\n[FINAL PARSE RESULTS] {results}")
        
        print("\nKeeping browser open for 30s. Close window or Ctrl+C to exit.")
        await asyncio.sleep(30)
        await context.close()

if __name__ == "__main__":
    asyncio.run(run_fidelity_test())
