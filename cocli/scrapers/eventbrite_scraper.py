import logging
import asyncio
import re
from datetime import datetime
from typing import List, Optional, cast, Union
from playwright.async_api import async_playwright

from bs4 import BeautifulSoup, Tag

from ..models.campaigns.events import Event
from ..core.text_utils import slugify

logger = logging.getLogger(__name__)

class EventbriteScraper:
    def __init__(self, debug: bool = False):
        self.debug = debug
        self.base_url = "https://www.eventbrite.com/d/ca--fullerton/events/"

    async def scrape_fullerton(self) -> List[Event]:
        events = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=not self.debug)
            context = await browser.new_context()
            page = await context.new_page()
            
            logger.info(f"Navigating to Eventbrite Fullerton: {self.base_url}")
            await page.goto(self.base_url, wait_until="networkidle")
            
            # Scroll to load more (Eventbrite uses lazy loading)
            for _ in range(3):
                await page.mouse.wheel(0, 2000)
                await asyncio.sleep(1)

            html = await page.content()
            if self.debug:
                with open("temp/eventbrite_debug.html", "w") as f:
                    f.write(html)

            soup = BeautifulSoup(html, "html.parser")
            
            # Eventbrite often uses 'SearchResultTile' or 'event-card'
            cards = soup.select('div[class*="SearchResultTile"]') or \
                    soup.select('div[class*="event-card"]') or \
                    soup.select('article')
            
            logger.info(f"Found {len(cards)} potential event cards.")

            for card in cards:
                try:
                    event = self._parse_card(card)
                    if event:
                        events.append(event)
                except Exception as e:
                    logger.error(f"Error parsing Eventbrite card: {e}")

            await browser.close()
        return events

    def _parse_card(self, card: Union[Tag, BeautifulSoup]) -> Optional[Event]:
        # Title and URL - Highly generic fallbacks
        title_elem = card.find('h3')
        if not title_elem:
            return None
        
        name = title_elem.get_text(strip=True)
        if not name:
            return None

        link_elem = card.find('a', href=True)
        url = str(link_elem.get('href')) if link_elem else ""
        if url and not url.startswith("http"):
            url = f"https://www.eventbrite.com{url}"

        # Date and Time
        # Look for text that looks like a date/time
        date_elem = card.find(string=re.compile(r'(Sun|Mon|Tue|Wed|Thu|Fri|Sat),'))
        date_str = str(date_elem).strip() if date_elem else "Unknown Date"
        
        # Image URL
        img_elem = card.find('img')
        image_url = cast(str, img_elem.get('src')) if img_elem else None

        # Host/Organizer - Usually near the location or at the bottom
        # We can look for specific footer classes or common patterns
        host_name = "Various Hosts"
        all_text = card.get_text(separator='|', strip=True).split('|')
        # Heuristic: The host is often one of the last few items
        if len(all_text) > 3:
            # Often [Title, Date, Location, Host]
            host_candidate = all_text[-1]
            if "followers" not in host_candidate.lower() and len(host_candidate) < 50:
                host_name = host_candidate

        # Simplified Date Parsing
        try:
            current_year = datetime.now().year
            # Match "Thu, Mar 19"
            match = re.search(r'([A-Z][a-z]{2}, [A-Z][a-z]{2} \d+)', date_str)
            if match:
                clean_date = match.group(1)
                dt = datetime.strptime(f"{clean_date} {current_year}", "%a, %b %d %Y")
            else:
                dt = datetime.now()
        except Exception:
            dt = datetime.now()

        return Event(
            start_time=dt,
            host_slug=slugify(host_name),
            event_slug=slugify(name),
            name=name,
            host_name=host_name,
            location="Fullerton, CA", # Default for now
            url=url if url else None,
            image_url=image_url,
            category="EventBrite",
            source_url=self.base_url
        )
