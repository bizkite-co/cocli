import asyncio
import argparse
import sys
import os
from io import StringIO
from playwright.async_api import async_playwright
from typing import Optional

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from cocli.models.google_maps_raw import GoogleMapsRawResult
from cocli.models.google_maps_prospect import GoogleMapsProspect
from cocli.utils.usv_utils import USVDictReader

async def fetch_metadata_via_playwright(page, place_id: str) -> Optional[GoogleMapsRawResult]:
    """
    Uses a single browser page to fetch metadata for a Place ID.
    Navigates to the direct Google Maps URL and extracts Name and Address from the card.
    """
    url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        
        # Wait for the main card to appear or a timeout
        # We look for the name which is usually in an h1
        try:
            await page.wait_for_selector('h1', timeout=10000)
        except Exception:
            pass
            
        name = await page.locator('h1').first.inner_text()
        
        # Address is often in a button with data-item-id="address"
        address = ""
        address_loc = page.locator('button[data-item-id="address"]')
        if await address_loc.is_visible():
            address = await address_loc.inner_text()

        if name and name != "Google Maps":
            # Basic address parsing
            street, city, state, zip_code = "", "", "", ""
            if address:
                # Remove the special icon char if present
                clean_address = address.replace("\ue0c8", "").strip()
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
                Full_Address=address,
                Street_Address=street,
                City=city,
                State=state,
                Zip=zip_code,
                processed_by="playwright-recovery-agent"
            )
    except Exception as e:
        print(f"Playwright fetch failed for {place_id}: {e}")
        
    return None

async def main():
    parser = argparse.ArgumentParser(description="Repopulate roadmap metadata using Playwright for hollow prospects.")
    parser.add_argument("--limit", type=int, default=1, help="Number of records to process.")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes.")
    parser.add_argument("--campaign", default="roadmap", help="Campaign name.")
    args = parser.parse_args()

    from cocli.core.reporting import get_boto3_session
    from cocli.core.config import load_campaign_config
    
    config = load_campaign_config(args.campaign)
    aws_config = config.get("aws", {})
    bucket = aws_config.get("data_bucket_name") or f"{args.campaign}-cocli-data-use1"

    session = get_boto3_session(config)
    s3 = session.client("s3")
    prefix = f"campaigns/{args.campaign}/indexes/google_maps_prospects/"
    
    # 1. Identify Hollow Files
    print(f"Searching for hollow prospects in S3 (bucket: {bucket})...")
    paginator = s3.get_paginator("list_objects_v2")
    hollow_keys = []
    
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".usv"):
                # Fast check: Size? Hollow files are usually small (~500 bytes)
                if obj["Size"] < 1000:
                    hollow_keys.append(obj["Key"])
                    if len(hollow_keys) >= args.limit:
                        break
        if len(hollow_keys) >= args.limit:
            break

    if not hollow_keys:
        print("No hollow prospects found.")
        return

    print(f"Found {len(hollow_keys)} potential hollow prospects. Starting Playwright...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        for key in hollow_keys:
            response = s3.get_object(Bucket=bucket, Key=key)
            content = response["Body"].read().decode("utf-8")
            reader = USVDictReader(StringIO(content))
            rows = list(reader)
            if not rows:
                continue
            
            row = rows[0]
            pid = row.get("Place_ID") or row.get("place_id")
            name = row.get("Name") or row.get("name")
            
            if not name or name == "None" or name == "":
                print(f"Repopulating {pid} ({key})...")
                raw_result = await fetch_metadata_via_playwright(page, pid)
                
                if raw_result and raw_result.Name:
                    print(f"  [SUCCESS] {raw_result.Name} | {raw_result.Full_Address}")
                    prospect = GoogleMapsProspect.from_raw(raw_result)
                    
                    if not args.dry_run:
                        s3.put_object(Bucket=bucket, Key=key, Body=prospect.to_usv().encode("utf-8"))
                else:
                    print(f"  [FAILED] Could not find metadata for {pid}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
