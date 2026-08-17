# POLICY: frictionless-data-policy-enforcement
import logging
import re
from typing import AsyncIterator, Set, Optional
from playwright.async_api import Page, Locator

from ....core.config import load_scraper_settings
from ....core.text_utils import slugify
from ....models.campaigns.indexes.google_maps_list_item import GoogleMapsListItem
from ....utils.headers import jittered_delay_ms
from .utils import get_tile_bounds

# Captures center lat/lon AND zoom - center alone isn't enough to detect a
# widened search (see _viewport_still_in_tile).
_MAP_STATE_RE = re.compile(r"@(-?\d+\.?\d*),(-?\d+\.?\d*),(\d+\.?\d*)z")

# Grid-mode navigation always requests 13z (Navigator.goto()/coordinator.py -
# a 0.1-degree tile is ~7 miles, sized for that zoom). Each zoom level roughly
# doubles the visible width, so even 1 level down covers ~2x the tile in each
# dimension - treat anything meaningfully below 13 as "no longer just this
# tile," not only a hard jump to a different center.
_GRID_MODE_ZOOM = 13.0
_MIN_ACCEPTABLE_ZOOM = 12.5

# Stop scanning after this many consecutive out-of-tile results, rather than
# discarding them one by one indefinitely - Google's sidebar increasingly
# intersperses distant results deeper into the scroll, so a run this long is
# a strong, cheap-to-check signal that everything further is more of the
# same, without waiting for the coarser URL-drift check (_viewport_still_in_tile)
# to catch up.
_MAX_CONSECUTIVE_OUT_OF_BOUNDS = 5

# How many scan-loop iterations between periodic block/CAPTCHA checks (each
# check fetches full page HTML via page.content(), so this isn't free to run
# every ~1s tick alongside the viewport check).
_BLOCK_CHECK_INTERVAL = 5

logger = logging.getLogger(__name__)

class SidebarScraper:
    def __init__(self, page: Page, debug: bool = False):
        self.page = page
        self.debug = debug
        self.settings = load_scraper_settings()

    def _viewport_still_in_tile(self, tile_id: Optional[str]) -> bool:
        """True if the page's current URL still reflects a view scoped to
        tile_id - both center point AND zoom level.

        Confirmed live 2026-08-16: a real tile+phrase scan ran 5+ minutes,
        successfully parsing ~90 real listings throughout, every single one
        discarded by the per-item geographic bounds filter - because Google
        progressively zoomed out *during* scrolling (13z -> 11z) to keep
        finding listings for the infinite-scroll feed, while the center
        point never drifted outside the tile bounds. A center-only,
        checked-once-up-front check cannot catch either half of that: not
        the zoom (center was fine), and not the timing (drift developed
        during the scroll loop, after any one-time initial check already
        passed). Call this every loop iteration instead - reading
        self.page.url is a local, synchronous, zero-network-cost check.
        """
        if not tile_id:
            return True
        bounds = get_tile_bounds(tile_id)
        if not bounds:
            return True
        match = _MAP_STATE_RE.search(self.page.url)
        if not match:
            return True
        center_lat = float(match.group(1))
        center_lon = float(match.group(2))
        zoom = float(match.group(3))
        in_bounds = (
            bounds["lat_min"] <= center_lat < bounds["lat_max"]
            and bounds["lon_min"] <= center_lon < bounds["lon_max"]
        )
        return in_bounds and zoom >= _MIN_ACCEPTABLE_ZOOM

    async def wait_for_hydration(self, listing_locator: Locator) -> bool:
        """
        Production-grade hydration wait. 
        Waits for the high-fidelity semantic ARIA label (stars + reviews) to appear.
        """
        combined_pattern = re.compile(r"\d\.\d\s*stars?\s*[\d,]+\s*Reviews?", re.IGNORECASE)
        
        try:
            await listing_locator.get_by_text(combined_pattern).first.wait_for(timeout=500)
            return True
        except Exception:
            try:
                await listing_locator.locator('span[aria-label*="stars"]').first.wait_for(timeout=200)
                return True
            except Exception:
                return False

    async def capture_listing_html(self, listing_locator: Locator) -> str:
        """Production method to capture the outerHTML of a listing div."""
        try:
            html = await listing_locator.evaluate("el => el.outerHTML")
            return str(html)
        except Exception:
            return ""

    async def scrape(
        self,
        search_string: str,
        processed_place_ids: Set[str],
        force_refresh: bool,
        ttl_days: int,
        tile_id: Optional[str] = None
    ) -> AsyncIterator[GoogleMapsListItem]:
        """
        Scrapes the sidebar results for the current map view.
        Yields GoogleMapsListItem for each found business.
        """
        from ..google_maps_parser import parse_business_listing_html

        logger.info(f"Scanning sidebar for: '{search_string}'")

        if self.page.is_closed():
            return

        try:
            scrollable_div_selector = 'div[role="feed"]'
            await self.page.wait_for_selector(scrollable_div_selector, timeout=20000)
            scrollable_div = self.page.locator(scrollable_div_selector)
        except Exception:
            logger.warning(f"Could not find scrollable results feed for '{search_string}'. Possibly no results.")
            from ....utils.alert_utils import check_and_alert_google_maps_block
            await check_and_alert_google_maps_block(
                self.page, f"No results feed for '{search_string}' (scanner.scrape)"
            )
            return

        # Google auto-resizes/recenters/zooms-out the viewport for sparse
        # areas (e.g. a tile over open ocean or a large desert) to keep
        # finding listings for the infinite-scroll feed - and does this
        # progressively AS THE SCAN SCROLLS, not only once at initial load.
        # The per-item bounds filter below already discards results from
        # outside the tile one-by-one, but each one still looks like "new"
        # DOM content to the stall-detector (consecutive_no_new_results
        # never trips), so a check that only runs once up front cannot catch
        # drift that develops later - confirmed live 2026-08-16: a real scan
        # ran 5+ minutes, successfully parsing ~90 real listings, all
        # discarded, because zoom dropped mid-scroll while the initial
        # up-front check had already passed. Check every loop iteration
        # instead (self.page.url is a local, zero-network-cost read).
        last_processed_div_count = 0
        consecutive_no_new_results = 0
        consecutive_out_of_bounds = 0
        stop_scan = False
        loop_iteration = 0

        while True:
            if self.page.is_closed():
                break

            # Periodic (not just reactive-on-exception) block/CAPTCHA check.
            # The 3 existing call sites (navigator.py x2, gm_details_scraper.py)
            # only fire when navigation/search already raised - a "soft" block
            # (page loads fine, shows a CAPTCHA/rate-limit page instead of
            # results) wouldn't necessarily throw, so a long-running scan could
            # sit on a block page indefinitely without ever tripping those.
            # Throttled to avoid a page.content() fetch every ~1s loop tick.
            loop_iteration += 1
            if loop_iteration % _BLOCK_CHECK_INTERVAL == 1:
                from ....utils.alert_utils import check_and_alert_google_maps_block
                if await check_and_alert_google_maps_block(
                    self.page, f"Periodic check during scan of '{search_string}'"
                ):
                    logger.warning(
                        f"Block detected mid-scan for '{search_string}' - stopping "
                        "this task's scan early."
                    )
                    break

            if not self._viewport_still_in_tile(tile_id):
                logger.info(
                    f"Viewport drifted outside tile {tile_id} for '{search_string}' "
                    f"during scan (now at {self.page.url}). Stopping - further "
                    "content would be discarded by the bounds filter anyway."
                )
                break

            await self.page.wait_for_timeout(jittered_delay_ms(1000))
            listing_divs = await scrollable_div.locator("> div").all()
            
            if len(listing_divs) == last_processed_div_count:
                consecutive_no_new_results += 1
                if consecutive_no_new_results > 2:
                    logger.debug("No new results after scrolling. Stopping.")
                    break
            else:
                consecutive_no_new_results = 0

            for i in range(last_processed_div_count, len(listing_divs)):
                if self.page.is_closed():
                    break
                    
                listing_div = listing_divs[i]
                
                try:
                    box = await listing_div.bounding_box()
                    if box:
                        await self.page.mouse.move(box['x'] + box['width']/2, box['y'] + box['height']/2)
                        await self.page.mouse.wheel(0, 100)
                        await self.page.wait_for_timeout(jittered_delay_ms(500))
                except Exception:
                    pass

                await self.wait_for_hydration(listing_div)
                html_content = await self.capture_listing_html(listing_div)

                if not html_content or "All filters" in html_content or "Prices come from Google" in html_content:
                    continue

                data = parse_business_listing_html(html_content, search_string, debug=self.debug)
                place_id = data.get("Place_ID")

                # Geographic Filtering (Targeted Tiles)
                # Google often intersperses results from outside the targeted area,
                # increasingly so deeper into the scroll. We strictly enforce 0.1
                # degree tile bounds to prevent cross-tile duplication, AND track a
                # consecutive-miss streak rather than only discarding one-by-one -
                # once several in a row land outside the tile, further scrolling is
                # overwhelmingly likely to keep finding more of the same, so stop
                # instead of continuing to hover/hydrate/parse items we already know
                # we'll discard.
                if tile_id:
                    bounds = get_tile_bounds(tile_id)
                    if bounds:
                        lat_val = data.get("Latitude")
                        lon_val = data.get("Longitude")
                        if lat_val and lon_val:
                            try:
                                lat_f: Optional[float] = float(lat_val)
                                lon_f: Optional[float] = float(lon_val)
                            except (ValueError, TypeError):
                                lat_f = lon_f = None
                            if lat_f is not None and lon_f is not None:
                                in_bounds = (
                                    bounds["lat_min"] <= lat_f < bounds["lat_max"]
                                    and bounds["lon_min"] <= lon_f < bounds["lon_max"]
                                )
                                if in_bounds:
                                    consecutive_out_of_bounds = 0
                                else:
                                    consecutive_out_of_bounds += 1
                                    if self.debug:
                                        logger.debug(f"Skipping out-of-bounds result: {data.get('Name')} at {lat_f}, {lon_f} for tile {tile_id}")
                                    if consecutive_out_of_bounds >= _MAX_CONSECUTIVE_OUT_OF_BOUNDS:
                                        logger.info(
                                            f"{consecutive_out_of_bounds} consecutive out-of-tile results "
                                            f"for '{search_string}' in tile {tile_id} - stopping instead "
                                            "of scrolling through more we'd discard anyway."
                                        )
                                        stop_scan = True
                                        break
                                    continue

                if place_id and place_id not in processed_place_ids:
                    processed_place_ids.add(place_id)
                    
                    # Type-safe field extraction
                    raw_revs = data.get("Reviews_count")
                    revs = int(str(raw_revs).replace(",", "")) if raw_revs else None
                    
                    raw_rating = data.get("Average_rating")
                    rating = float(str(raw_rating)) if raw_rating else None

                    item = GoogleMapsListItem(
                        place_id=place_id,
                        name=data.get("Name", "Unknown"),
                        category=data.get("First_category"),
                        company_slug=data.get("company_slug", slugify(data.get("Name", place_id))),
                        phone=data.get("Phone_1"),
                        domain=data.get("Domain"),
                        reviews_count=revs,
                        average_rating=rating,
                        street_address=data.get("Street_Address"),
                        gmb_url=data.get("GMB_URL"),
                        discovery_phrase=search_string,
                        discovery_tile_id=tile_id,
                        html=html_content
                    )
                    yield item

            if stop_scan:
                break

            last_processed_div_count = len(listing_divs)
            
            try:
                await scrollable_div.hover()
                await self.page.mouse.wheel(0, 5000)
                await self.page.wait_for_timeout(jittered_delay_ms(2000))
            except Exception:
                break
