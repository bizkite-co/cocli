import asyncio
from pathlib import Path
from typing import Any
from playwright.async_api import async_playwright
import typer
from bs4 import BeautifulSoup
from cocli.core.text_utils import slugify
from cocli.utils.headers import ANTI_BOT_HEADERS, USER_AGENT

async def capture_pipeline(page: Any, name: str, phrase: str, lat: str, lon: str, base_dir: Path) -> None:
    print(f"Processing {name}...")
    
    # 1. Search Phase
    url = f"https://www.google.com/maps/search/{phrase}/@{lat},{lon},15z"
    print(f"  Searching: {url}")
    try:
        await page.goto(url, wait_until="load", timeout=60000)
        # Wait for the results pane (role="main" or role="feed")
        await page.wait_for_selector('div[role="main"], div[role="feed"]', timeout=30000)
        await asyncio.sleep(10)
        
        list_content = await page.content()
        (base_dir / "list.html").write_text(list_content, encoding="utf-8")
        print("    ✓ Saved list.html")
        
        # 2. Semantic Link Extraction (Find <a> where aria-label contains the name)
        soup = BeautifulSoup(list_content, "html.parser")
        target_link = None
        
        # Google Maps uses <a> tags with aria-label="Business Name" for the main links
        for a in soup.find_all("a", attrs={"aria-label": True}):
            label = a.get("aria-label", "")
            if isinstance(label, str) and name.lower() in label.lower():
                target_link = str(a.get("href", ""))
                break
        
        if not target_link:
            print(f"    ✗ Could not find semantic GMB_URL for {name} in list.html")
            return

        if target_link.startswith("/"):
            target_link = "https://www.google.com" + target_link
            
        print(f"  Following Semantic Link: {target_link}")
        
        # 3. Detail Phase
        await page.goto(target_link, wait_until="load", timeout=60000)
        # Wait for the specific business name headline or the main detail role
        await page.wait_for_selector('div[role="main"]', timeout=30000)
        await asyncio.sleep(10)
        
        item_content = await page.content()
        (base_dir / "item.html").write_text(item_content, encoding="utf-8")
        print("    ✓ Saved item.html")
        
    except Exception as e:
        print(f"    ✗ Pipeline failed: {e}")

def main(
    usv_path: Path = Path("tests/data/maps.google.com/golden_set.usv")
) -> None:
    if not usv_path.exists():
        print(f"Error: {usv_path} not found.")
        return
    
    async def run_all() -> None:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=USER_AGENT, extra_http_headers=ANTI_BOT_HEADERS)
            page = await context.new_page()

            with open(usv_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split("\x1f")
                    if len(parts) < 8:
                        continue
                    
                    name, addr, ph, web, pid, phrase, lat, lon = parts
                        
                    slug = slugify(name)
                    base_dir = Path("tests/data/maps.google.com/snapshots") / slug
                    base_dir.mkdir(parents=True, exist_ok=True)

                    await capture_pipeline(page, name, phrase, lat, lon, base_dir)

            await browser.close()

    asyncio.run(run_all())

if __name__ == "__main__":
    typer.run(main)
