import asyncio
from playwright.async_api import async_playwright

async def debug_granite_final() -> None:
    url = "https://www.google.com/maps/place/Granite+Financial+Partners/@42.8723844,-71.6120805,17z/data=!3m1!4b1!4m6!3m5!1s0x89e3cbdf2911af9d:0xeb9579937fc14183!8m2!3d42.8723844!4d-71.6120805!16s%2Fg%2F1pxwn0s47"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Use a real browser context
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="load")
            await asyncio.sleep(15)
            
            # Action: Get the outerText of the entire body to avoid separator issues
            body_text = await page.evaluate("() => document.body.innerText")
            
            # Action: Target specifically the button area
            button_text = await page.evaluate("""() => {
                return Array.from(document.querySelectorAll('button'))
                    .map(b => b.innerText)
                    .filter(t => t.toLowerCase().includes('review'));
            }""")
            
            print("--- BODY TEXT SAMPLE ---")
            print(body_text.replace('\n', ' ')[:1000])
            print("\n--- BUTTON TEXTS ---")
            print(str(button_text))

        except Exception as e:
            print("Error: " + str(e))
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_granite_final())
