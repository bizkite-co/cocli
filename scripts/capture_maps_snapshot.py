# POLICY: frictionless-data-policy-enforcement
import asyncio
import time
from pathlib import Path
from typing import Any, List, Dict
from playwright.async_api import async_playwright
import typer
from bs4 import BeautifulSoup
from cocli.core.text_utils import slugify
from cocli.utils.headers import ANTI_BOT_HEADERS, USER_AGENT

app = typer.Typer()

GOLDEN_SET_PATH = Path("tests/data/maps.google.com/golden_set.usv")
SNAPSHOT_DIR = Path("tests/data/maps.google.com/snapshots")

async def capture_pipeline(page: Any, name: str, phrase: str, lat: str, lon: str, base_dir: Path) -> bool:
    """Captures list.html and item.html for a given location."""
    print(f"Processing {name}...")
    base_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Search Phase
    url = f"https://www.google.com/maps/search/{phrase}/@{lat},{lon},15z"
    print(f"  Searching: {url}")
    try:
        await page.goto(url, wait_until="load", timeout=60000)
        # Wait for the results pane (role="main" or role="feed")
        await page.wait_for_selector('div[role="main"], div[role="feed"]', timeout=30000)
        # Google Maps needs a bit of settling time for dynamic content
        await asyncio.sleep(5)
        
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
            # Fallback: if there's only one result, Google might have auto-redirected to the item page
            # We check if we are already on an item page (contains /maps/place/)
            if "/maps/place/" in page.url:
                print("    ! Already on item page (auto-redirect)")
                item_content = await page.content()
                (base_dir / "item.html").write_text(item_content, encoding="utf-8")
                print("    ✓ Saved item.html")
                return True
            return False

        if target_link.startswith("/"):
            target_link = "https://www.google.com" + target_link
            
        print(f"  Following Semantic Link: {target_link}")
        
        # 3. Detail Phase
        await page.goto(target_link, wait_until="load", timeout=60000)
        # Wait for the specific business name headline or the main detail role
        await page.wait_for_selector('div[role="main"]', timeout=30000)
        await asyncio.sleep(5)
        
        item_content = await page.content()
        (base_dir / "item.html").write_text(item_content, encoding="utf-8")
        print("    ✓ Saved item.html")
        return True
        
    except Exception as e:
        print(f"    ✗ Pipeline failed for {name}: {e}")
        return False

def get_golden_data() -> List[Dict[str, str]]:
    if not GOLDEN_SET_PATH.exists():
        return []
    
    test_cases = []
    with open(GOLDEN_SET_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\x1f")
            if len(parts) >= 8:
                test_cases.append({
                    "name": parts[0],
                    "address": parts[1],
                    "phone": parts[2],
                    "website": parts[3],
                    "place_id": parts[4],
                    "search_phrase": parts[5],
                    "lat": parts[6],
                    "lon": parts[7],
                    "slug": slugify(parts[0])
                })
    return test_cases

async def run_capture(force: bool = False) -> None:
    """Runs the capture pipeline for all items in the golden set if they are stale."""
    data = get_golden_data()
    if not data:
        print("Golden set is empty.")
        return

    stale_items = []
    for item in data:
        base_dir = SNAPSHOT_DIR / item["slug"]
        list_file = base_dir / "list.html"
        item_file = base_dir / "item.html"
        
        if not list_file.exists() or not item_file.exists() or force:
            stale_items.append(item)
        else:
            # Check age (24 hours)
            mtime = list_file.stat().st_mtime
            if (time.time() - mtime) > 86400:
                stale_items.append(item)

    if not stale_items:
        print("All snapshots are fresh (< 24h old).")
        return

    print(f"Refreshing {len(stale_items)} stale snapshots...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=USER_AGENT, extra_http_headers=ANTI_BOT_HEADERS)
        page = await context.new_page()

        for item in stale_items:
            base_dir = SNAPSHOT_DIR / item["slug"]
            await capture_pipeline(page, item["name"], item["search_phrase"], item["lat"], item["lon"], base_dir)

        await browser.close()

@app.command()
def main(
    force: bool = typer.Option(False, "--force", "-f", help="Force refresh even if not stale")
) -> None:
    asyncio.run(run_capture(force=force))

if __name__ == "__main__":
    app()
