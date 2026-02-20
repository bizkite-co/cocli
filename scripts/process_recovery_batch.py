import asyncio
import argparse
import sys
import os
import random
import time
from typing import List, Optional, Any
from playwright.async_api import async_playwright

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from cocli.models.campaigns.indexes.google_maps_raw import GoogleMapsRawResult
from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
from cocli.utils.headers import ANTI_BOT_HEADERS, USER_AGENT

# Unit Separator Standard
US = "\x1f"
RS = "\n"

async def fetch_metadata_via_playwright(page: Any, place_id: str) -> Optional[GoogleMapsRawResult]:
    url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"
    try:
        # Randomized initial wait to break patterns
        await page.wait_for_timeout(random.randint(2000, 5000))
        
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        
        # Human-like delay after navigation
        await page.wait_for_timeout(random.randint(3000, 7000))
        
        try:
            await page.wait_for_selector('h1', timeout=10000)
        except Exception:
            pass
            
        name = await page.locator('h1').first.inner_text()
        address = ""
        address_loc = page.locator('button[data-item-id="address"]')
        if await address_loc.is_visible():
            address = await address_loc.inner_text()

        if name and name != "Google Maps":
            street, city, state, zip_code = "", "", "", ""
            if address:
                clean_address = address.replace("\ue0c8", "").strip().replace("\n", " ")
                parts = [p.strip() for p in clean_address.split(",")]
                if len(parts) >= 3:
                    street = parts[0]
                    city = parts[1]
                    state_zip = parts[2].split(" ")
                    state = state_zip[0]
                    if len(state_zip) > 1:
                        zip_code = state_zip[1]

            return GoogleMapsRawResult(
                Place_ID=place_id,
                Name=name,
                Full_Address=address.replace("\n", " "),
                Street_Address=street,
                City=city,
                State=state,
                Zip=zip_code,
                processed_by="batch-recovery-playwright"
            )
    except Exception as e:
        print(f"  [ERROR] Playwright fetch failed for {place_id}: {e}")
        
    return None

async def process_batch(place_ids: List[str], campaign_name: str, bucket: str, recovery_dir: str, dry_run: bool = False) -> None:
    batch_start = time.time()
    print(f"Processing batch of {len(place_ids)} Place IDs with rate-limiting...")
    
    from cocli.core.reporting import get_boto3_session
    from cocli.core.config import load_campaign_config
    
    config = load_campaign_config(campaign_name)
    session = get_boto3_session(config)
    s3 = session.client("s3")
    prefix = f"campaigns/{campaign_name}/indexes/google_maps_prospects/"
    healed_index_path = os.path.join(recovery_dir, "healed_prospects_index.usv")
    
    success_count = 0
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=USER_AGENT,
            extra_http_headers=ANTI_BOT_HEADERS
        )
        page = await context.new_page()

        for pid in place_ids:
            start_time = time.time()
            print(f"  Target: {pid}...", end="", flush=True)
            
            raw_result = await fetch_metadata_via_playwright(page, pid)

            if raw_result and raw_result.Name:
                success_count += 1
                print(f" SUCCESS: {raw_result.Name}", end="")
                prospect = GoogleMapsProspect.from_raw(raw_result)
                
                if not dry_run:
                    key = f"{prefix}{pid}.usv"
                    s3.put_object(Bucket=bucket, Key=key, Body=prospect.to_usv().encode("utf-8"))
                    
                    with open(healed_index_path, "a", encoding="utf-8") as f:
                        fields = [
                            prospect.place_id, 
                            prospect.name or "", 
                            prospect.company_slug or "", 
                            prospect.city or "", 
                            prospect.state or "", 
                            prospect.zip or ""
                        ]
                        f.write(US.join(fields) + RS)
            else:
                print(" FAILED", end="")
            
            elapsed = time.time() - start_time
            print(f" ({elapsed:.1f}s)")
            
            # Optimized delay: 4-8 seconds
            if pid != place_ids[-1]:
                await asyncio.sleep(random.uniform(4, 8))

        await browser.close()

    total_elapsed = time.time() - batch_start
    avg_per_record = total_elapsed / len(place_ids) if place_ids else 0
    print(f"\nBatch completed in {total_elapsed:.1f}s.")
    print(f"Success Rate: {success_count}/{len(place_ids)}")
    print(f"Average: {avg_per_record:.2f}s per record.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10, help="Number of items from the hollow list to process.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--campaign", default="roadmap", help="Campaign name.")
    args = parser.parse_args()
    
    from cocli.core.config import load_campaign_config
    CAMPAIGN = args.campaign
    config = load_campaign_config(CAMPAIGN)
    RECOVERY_DIR = f"/home/mstouffer/.local/share/cocli_data/campaigns/{CAMPAIGN}/recovery"
    HOLLOW_LIST = os.path.join(RECOVERY_DIR, "hollow_place_ids.usv")
    
    aws_config = config.get("aws", {})
    BUCKET = aws_config.get("data_bucket_name") or aws_config.get("cocli_data_bucket_name") or f"{CAMPAIGN}-cocli-data-use1"
    
    if not os.path.exists(HOLLOW_LIST):
        print(f"Error: {HOLLOW_LIST} not found.")
        sys.exit(1)

    # Read the next N items from the hollow list
    with open(HOLLOW_LIST, "r") as f:
        all_hollow = [line.strip() for line in f if line.strip()]
    
    # Check healed index to subtract already processed
    healed_index_path = os.path.join(RECOVERY_DIR, "healed_prospects_index.usv")
    already_healed = set()
    if os.path.exists(healed_index_path):
        with open(healed_index_path, "r") as f:
            for line in f:
                parts = line.split(US)
                if parts:
                    already_healed.add(parts[0])

    to_process = []
    for pid in all_hollow:
        if pid not in already_healed:
            to_process.append(pid)
            if len(to_process) >= args.limit:
                break

    if not to_process:
        print("No remaining hollow Place IDs to process.")
    else:
        asyncio.run(process_batch(to_process, BUCKET, RECOVERY_DIR, args.dry_run))