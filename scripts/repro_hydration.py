# POLICY: frictionless-data-policy-enforcement
import asyncio
import logging
from playwright.async_api import async_playwright
from cocli.utils.playwright_utils import setup_optimized_context

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("alignment_test")

async def run_alignment_test() -> None:
    # Target: Griffith Observatory FULL URL (Proven stable)
    url = "https://www.google.com/maps/place/Griffith+Observatory/@34.1184341,-118.3003935,17z/data=!4m6!3m5!1s0x80c2bf61e9d408cb:0x73ff07b1c2d6dadc!8m2!3d34.1184341!4d-118.3003935!16zL20vMDJfNG1s"
    
    print("\n--- GM-LIST ALIGNMENT TEST ---")
    print("Strategy: Clone the successful gm-list configuration.")
    print("Viewport: 2000x2000")
    print("Headers: STOCK (No overrides)")
    print("Optimizations: ENABLED (CSS/Image blocking)")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        
        # 1. Create context exactly like ScrapeCoordinator
        context = await browser.new_context(
            viewport={'width': 2000, 'height': 2000}
        )
        
        # 2. Setup optimized context (BLOCKS CSS/Images)
        # This is what discovery uses!
        await setup_optimized_context(context)
        
        page = await context.new_page()
        
        logger.info("Navigating...")
        await page.goto(url, wait_until="commit")
        
        print("\n[MANUAL VERIFICATION]")
        print("1. Is the page in 'Limited View'?")
        print("2. Is the review count (17,059) visible in the sidebar?")
        print("\nPress ENTER here to capture and parse.")
        
        await asyncio.to_thread(input, "Press ENTER to capture...")

        # Capture and Parse with our PRODUCTION logic
        from bs4 import BeautifulSoup
        from cocli.scrapers.google_maps_parsers.extract_rating_reviews_gm_details import extract_rating_reviews_gm_details
        
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")
        results = extract_rating_reviews_gm_details(soup, soup.get_text(), debug=True)
        
        print(f"\n[PARSER RESULTS] {results}")
        
        print("\nClose the window to exit.")
        stop_event = asyncio.Event()
        browser.on("disconnected", lambda _: stop_event.set())
        await stop_event.wait()

if __name__ == "__main__":
    asyncio.run(run_alignment_test())
