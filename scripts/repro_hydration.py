# POLICY: frictionless-data-policy-enforcement
import asyncio
import logging
from playwright.async_api import async_playwright
from cocli.utils.headers import ANTI_BOT_HEADERS, USER_AGENT
from cocli.scrapers.google_maps_details import capture_google_maps_raw

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("final_test")

async def run_final_test() -> None:
    # Griffith Observatory
    place_id = "ChIJywjU6WG_woAR3NrWwrEH_3M"
    campaign = "roadmap"
    
    print("\n--- FINAL PRODUCTION PIPELINE TEST ---")
    print("Includes: Pre-Flight Warmup, Session-Heal, Ultra-Robust Parser")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent=USER_AGENT,
            extra_http_headers=ANTI_BOT_HEADERS,
            viewport={'width': 1920, 'height': 1080}
        )
        page = await context.new_page()
        
        # Use our PRODUCTION capture function
        witness = await capture_google_maps_raw(page, place_id, campaign, debug=True)
        
        if witness:
            from bs4 import BeautifulSoup
            from cocli.scrapers.google_maps_parsers.extract_rating_reviews import extract_rating_reviews
            soup = BeautifulSoup(witness.html, "html.parser")
            results = extract_rating_reviews(soup, soup.get_text(), debug=True)
            
            print(f"\n[FINAL RESULTS] {results}")
            if results.get("Reviews_count") == "17059":
                print("✅ PIEPLINE VERIFIED: Full reviews captured!")
            else:
                print(f"❌ STILL LITE: Captured {results.get('Reviews_count')} reviews.")
        else:
            print("❌ CAPTURE FAILED.")

        print("\nClose browser to finish.")
        stop_event = asyncio.Event()
        browser.on("disconnected", lambda: stop_event.set())
        await stop_event.wait()

if __name__ == "__main__":
    asyncio.run(run_final_test())
