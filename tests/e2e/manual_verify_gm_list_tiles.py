#!/usr/bin/env python3
"""Manual, interactive verification tool for the gm-list scraper.

NOT an automated pytest test - deliberately not named test_*.py so normal
pytest collection (including `make test-e2e`) never picks it up and hangs.
It opens a real, headed browser and waits for a human to close it before
continuing, which cannot run unattended in CI.

Runs a real browser against real Google Maps for a handful of tiles that
historically returned many results, using the exact same Navigator/
SidebarScraper code the production worker uses. After each tile it takes a
screenshot and leaves the browser window open for you to inspect (zoom in,
check for CAPTCHA/block pages, watch the scan happen); closing the window
moves on to the next tile.

Built 2026-08-16 to visually confirm the gm-list navigation fix (see
task-agent ticket
regression-gm-list-stuck-at-60-for-months-broken-stealth-script-and-no-backoff-on-google-block-detection)
is finding real results without tripping Google's bot detection, now that
real production-shaped searches are going through the corrected navigation
path for the first time in 164 days.

Usage:
    uv run python3 tests/e2e/manual_verify_gm_list_tiles.py
    uv run python3 tests/e2e/manual_verify_gm_list_tiles.py --campaign turboship --tiles 5 --min-rows 30
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from playwright.async_api import Browser, async_playwright

from cocli.core.config import get_campaign_exports_dir
from cocli.core.paths import paths
from cocli.scrapers.google.gm_scraper.navigator import Navigator
from cocli.scrapers.google.gm_scraper.scanner import SidebarScraper


def find_high_yield_tiles(
    campaign_name: str, min_rows: int, limit: int
) -> list[tuple[str, str, float, float, Path]]:
    """Returns (tile_id, phrase, lat, lon, source_file), highest row-count
    first, deduplicated by tile so each browser session covers a genuinely
    different location rather than the same tile's other search phrases."""
    results_root = paths.campaign(campaign_name).queue("gm-list").completed / "results"
    candidates: list[tuple[int, str, str, float, float, Path]] = []

    for f in results_root.rglob("*.usv"):
        parts = f.relative_to(results_root).parts
        if len(parts) < 3:
            continue
        try:
            lat = float(parts[-3])
            lon = float(parts[-2])
        except ValueError:
            continue
        try:
            n = sum(1 for line in f.read_text(errors="replace").split("\n") if line.strip())
        except OSError:
            continue
        if n < min_rows:
            continue
        phrase = f.stem.replace("-", " ")
        candidates.append((n, f"{lat}_{lon}", phrase, lat, lon, f))

    candidates.sort(key=lambda c: c[0], reverse=True)

    seen_tiles: set[str] = set()
    picked: list[tuple[str, str, float, float, Path]] = []
    for n, tile_id, phrase, lat, lon, src in candidates:
        if tile_id in seen_tiles:
            continue
        seen_tiles.add(tile_id)
        picked.append((tile_id, phrase, lat, lon, src))
        if len(picked) >= limit:
            break
    return picked


def find_zero_result_tiles(
    campaign_name: str, limit: int
) -> list[tuple[str, str, float, float, Path]]:
    """Returns (tile_id, phrase, lat, lon, receipt_file) for real completed
    gm-list tasks that recorded result_count == 0 - a .json completion
    receipt under gm-list/completed/results with no sibling .usv (no data
    file was ever written because nothing was found). Deduplicated by tile
    so each browser session covers a genuinely different location.

    For visually confirming whether these are true negatives (nothing
    there) or bugged negatives (navigation/viewport-drift silently
    discarded real results) - see task-agent ticket
    regression-gm-list-stuck-at-60-for-months-broken-stealth-script-and-no-backoff-on-google-block-detection.
    """
    import json

    results_root = paths.campaign(campaign_name).queue("gm-list").completed / "results"
    candidates: list[tuple[str, str, str, float, float, Path]] = []  # (completed_at, tile_id, phrase, lat, lon, src)

    for f in results_root.rglob("*.json"):
        if f.name in ("datapackage.json", "schema_ledger.json"):
            continue
        if f.with_suffix(".usv").exists():
            continue  # has data - not a zero-result receipt
        try:
            receipt = json.loads(f.read_text(errors="replace"))
        except (OSError, ValueError):
            continue
        if receipt.get("result_count") != 0:
            continue
        lat = receipt.get("latitude")
        lon = receipt.get("longitude")
        phrase = receipt.get("search_phrase")
        if lat is None or lon is None or not phrase:
            continue
        completed_at = str(receipt.get("completed_at", ""))
        candidates.append((completed_at, f"{lat}_{lon}", phrase, float(lat), float(lon), f))

    candidates.sort(key=lambda c: c[0], reverse=True)  # most recent first

    seen_tiles: set[str] = set()
    picked: list[tuple[str, str, float, float, Path]] = []
    for _completed_at, tile_id, phrase, lat, lon, src in candidates:
        if tile_id in seen_tiles:
            continue
        seen_tiles.add(tile_id)
        picked.append((tile_id, phrase, lat, lon, src))
        if len(picked) >= limit:
            break
    return picked


async def wait_for_close(browser: Browser) -> None:
    """Blocks until the user closes the browser window."""
    loop = asyncio.get_event_loop()
    fut: asyncio.Future[None] = loop.create_future()

    def _on_disconnected(_browser: Browser) -> None:
        if not fut.done():
            fut.set_result(None)

    browser.on("disconnected", _on_disconnected)
    await fut


async def run_one(
    index: int,
    total: int,
    tile_id: str,
    phrase: str,
    lat: float,
    lon: float,
    screenshot_dir: Path,
) -> None:
    print(f"\n{'=' * 70}")
    print(f"[{index}/{total}] tile={tile_id} phrase={phrase!r} center=({lat},{lon})")
    print(f"{'=' * 70}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=["--start-maximized"])
        context = await browser.new_context(no_viewport=True)
        page = await context.new_page()

        navigator = Navigator(page)
        scanner = SidebarScraper(page, debug=True)

        success = await navigator.goto(lat, lon, 8.0, 8.0, phrase)
        print(f"navigator.goto() success={success}")
        print(f"Settled URL: {page.url}")

        if success:
            items = []
            async for item in scanner.scrape(
                phrase, set(), force_refresh=False, ttl_days=30, tile_id=tile_id
            ):
                items.append(item)
                print(f"  found: {item.name!r} ({item.place_id})")
            print(f"\nScan complete: {len(items)} in-bounds item(s) yielded.")

            screenshot_dir.mkdir(parents=True, exist_ok=True)
            screenshot_path = screenshot_dir / f"tile_{index}_{tile_id}.png"
            try:
                await page.screenshot(path=str(screenshot_path))
                print(f"Screenshot saved: {screenshot_path}")
            except Exception as e:
                print(f"Screenshot failed (window may already be closing): {e}")

        print("\nBrowser window left open for inspection. Close it to continue...")
        await wait_for_close(browser)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", default="turboship")
    parser.add_argument("--tiles", type=int, default=3, help="Number of tiles to run")
    parser.add_argument(
        "--min-rows", type=int, default=20, help="Minimum historical result count to qualify a tile"
    )
    parser.add_argument(
        "--zero-results",
        action="store_true",
        help="Instead of high-yield tiles, select real completed tasks that recorded "
        "result_count == 0 (a .json receipt with no sibling .usv) - for visually "
        "confirming whether these are true negatives or bugged negatives.",
    )
    parser.add_argument("--screenshot-dir", type=Path, default=None)
    parser.add_argument(
        "--tile-id",
        default=None,
        help="Explicit tile to run instead of auto-selecting by historical row count, "
        "e.g. '33.9_-118.7' (southwest-corner lat_lon, underscore-joined).",
    )
    parser.add_argument(
        "--phrase", default=None, help="Search phrase to use with --tile-id (required together)."
    )
    args = parser.parse_args()

    screenshot_dir = args.screenshot_dir or (
        get_campaign_exports_dir(args.campaign) / "gm_list_manual_verify"
    )

    if args.tile_id:
        if not args.phrase:
            parser.error("--tile-id requires --phrase")
        lat_str, lon_str = args.tile_id.split("_")
        tiles = [(args.tile_id, args.phrase, float(lat_str) + 0.05, float(lon_str) + 0.05, Path("<explicit>"))]
    elif args.zero_results:
        tiles = find_zero_result_tiles(args.campaign, args.tiles)
    else:
        tiles = find_high_yield_tiles(args.campaign, args.min_rows, args.tiles)
    if not tiles:
        if args.zero_results:
            print(f"No result_count==0 completions found for campaign {args.campaign}.")
        else:
            print(f"No tiles found with >= {args.min_rows} historical rows for campaign {args.campaign}.")
        return

    print(f"Selected {len(tiles)} tile(s):")
    for tile_id, phrase, lat, lon, src in tiles:
        print(f"  {tile_id} | {phrase!r} | source: {src}")

    for i, (tile_id, phrase, lat, lon, _src) in enumerate(tiles, 1):
        await run_one(i, len(tiles), tile_id, phrase, lat, lon, screenshot_dir)

    print(f"\nAll tiles complete. Screenshots in {screenshot_dir}")


if __name__ == "__main__":
    asyncio.run(main())
