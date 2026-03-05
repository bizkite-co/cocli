import asyncio
import os
from playwright.async_api import async_playwright
from cocli.scrapers.google_maps_parsers.extract_rating_reviews_gm_details import extract_rating_reviews_gm_details
from cocli.utils.headers import ANTI_BOT_HEADERS, USER_AGENT
from bs4 import BeautifulSoup

async def capture_and_test(name: str, url: str) -> None:
    print("\n--- Testing: " + name + " ---")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Use OFFICIAL published headers and constants
        context = await browser.new_context(
            user_agent=USER_AGENT,
            extra_http_headers=ANTI_BOT_HEADERS,
            viewport={'width': 1280, 'height': 1024}
        )
        page = await context.new_page()
        print("Navigating to " + url)
        try:
            # Wait for 'load' then manual sleep for JS settle
            await page.goto(url, wait_until="load", timeout=60000)
            await asyncio.sleep(10) 
            
            html = await page.content()
            inner_text = await page.evaluate("() => document.body.innerText")
            
            soup = BeautifulSoup(html, "html.parser")
            result = extract_rating_reviews_gm_details(soup, inner_text, debug=True)
            
            print("Captured Result: " + str(result))
            
            os.makedirs(".logs", exist_ok=True)
            log_path = ".logs/repro_" + name.lower() + ".html"
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(html)
            print("Saved HTML to " + log_path)
                
        except Exception as e:
            print("Error: " + str(e))
        finally:
            await browser.close()

async def main() -> None:
    # Granite Financial Partners
    await capture_and_test("granite", "https://www.google.com/maps/place/Granite+Financial+Partners/@42.8723844,-71.6120805,17z/data=!3m1!4b1!4m6!3m5!1s0x89e3cbdf2911af9d:0xeb9579937fc14183!8m2!3d42.8723844!4d-71.6120805!16s%2Fg%2F1pxwn0s47")
    
    # Griffith Observatory
    await capture_and_test("griffith", "https://www.google.com/maps/place/Griffith+Observatory/@34.11856,-118.30037,15z/data=!4m2!3m1!1s0x0:0x33ff7ab1c2d6dabdc")

if __name__ == "__main__":
    asyncio.run(main())
