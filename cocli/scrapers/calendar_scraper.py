import logging
import asyncio
import re
from datetime import datetime
from typing import List, cast
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

from ..models.campaigns.events import Event
from ..core.text_utils import slugify

logger = logging.getLogger(__name__)

class CalendarScraper:
    def __init__(self, debug: bool = False):
        self.debug = debug

    async def scrape_fullerton_observer(self) -> List[Event]:
        url = "https://fullertonobserver.com/events/"
        events = []
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=not self.debug)
            context = await browser.new_context()
            page = await context.new_page()
            
            logger.info(f"Navigating to Fullerton Observer Calendar: {url}")
            await page.goto(url, wait_until="networkidle")
            
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")
            
            # The Events Calendar selectors
            items = soup.select('.tribe-events-calendar-list__event') or \
                    soup.select('.type-tribe_events')
            
            logger.info(f"Found {len(items)} Observer events.")

            for item in items:
                try:
                    title_elem = item.select_one('.tribe-events-calendar-list__event-title a, .tribe-events-list-event-title a')
                    if not title_elem:
                        continue
                    
                    name = title_elem.get_text(strip=True)
                    full_url = str(title_elem.get('href')) if title_elem.get('href') else ""

                    date_elem = item.select_one('.tribe-events-calendar-list__event-datetime, .tribe-events-event-schedule-details')
                    date_str = date_elem.get_text(strip=True) if date_elem else "Unknown Date"
                    
                    # Venue
                    venue_elem = item.select_one('.tribe-events-calendar-list__event-venue, .tribe-events-venue-details')
                    location = venue_elem.get_text(strip=True) if venue_elem else "Fullerton, CA"

                    # Image URL
                    img_elem = item.select_one('img')
                    image_url = cast(str, img_elem.get('src')) if img_elem else None

                    # Parse Date
                    try:
                        # "March 11 @ 8:00 am - 5:00 pm" or "February 18, 2026 @ 8:30 am"
                        # We'll use a simplified parser for now
                        current_year = datetime.now().year
                        match = re.search(r'([A-Z][a-z]+ \d+)', date_str)
                        if match:
                            clean_date = match.group(1)
                            dt = datetime.strptime(f"{clean_date} {current_year}", "%B %d %Y")
                        else:
                            dt = datetime.now()
                    except Exception:
                        dt = datetime.now()

                    event = Event(
                        start_time=dt,
                        host_slug="fullerton-observer",
                        event_slug=slugify(name),
                        name=name,
                        host_name="Fullerton Observer",
                        location=location,
                        url=full_url,
                        image_url=image_url,
                        category="News/Community",
                        source_url=url
                    )
                    events.append(event)
                except Exception as e:
                    logger.error(f"Error parsing Observer event: {e}")

            await browser.close()
        return events

    async def scrape_fullerton_library(self) -> List[Event]:
        url = "https://fullertonlibrary.org/calendar"
        events = []
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=not self.debug)
            context = await browser.new_context()
            page = await context.new_page()
            
            logger.info(f"Navigating to Fullerton Library Calendar: {url}")
            await page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(5) # Wait for AJAX

            html = await page.content()
            if self.debug:
                with open("temp/library_debug.html", "w") as f:
                    f.write(html)

            soup = BeautifulSoup(html, "html.parser")
            
            # Stacks often uses a grid. Look for any item that looks like a cell or card
            items = soup.select('.stacks-event') or \
                    soup.select('.views-row') or \
                    soup.select('.event-item')
            
            if not items:
                # Fallback: Look for any link that has /event/ in it
                links = soup.find_all('a', href=re.compile(r'/event/'))
                logger.info(f"Found {len(links)} links with /event/")
                for link in links:
                    name = link.get_text(strip=True)
                    if not name or len(name) < 3:
                        continue
                    
                    href = link.get('href')
                    full_url = str(href) if href else ""
                    if not full_url.startswith("http"):
                        full_url = f"https://fullertonlibrary.org{full_url}"
                    
                    event = Event(
                        start_time=datetime.now(), # Placeholder
                        host_slug="fullerton-public-library",
                        event_slug=slugify(name),
                        name=name,
                        host_name="Fullerton Public Library",
                        location="Fullerton Public Library",
                        url=full_url,
                        category="Educational",
                        source_url=url
                    )
                    events.append(event)
                return events

            logger.info(f"Found {len(items)} potential event elements.")

            for item in items:
                try:
                    title_elem = item.select_one(".event-title, h3, h2")
                    if not title_elem:
                        continue
                    
                    name = title_elem.get_text(strip=True)
                    
                    desc_elem = item.select_one(".event-teaser, .description, .teaser")
                    description = desc_elem.get_text(strip=True) if desc_elem else ""

                    # Link
                    link_elem = item.select_one("a")
                    href = link_elem.get("href") if link_elem else ""
                    url_path = str(href) if href else ""
                    full_url = url_path if url_path.startswith("http") else f"https://fullertonlibrary.org{url_path}"

                    event = Event(
                        start_time=datetime.now(), 
                        host_slug="fullerton-public-library",
                        event_slug=slugify(name),
                        name=name,
                        host_name="Fullerton Public Library",
                        location="Fullerton Public Library, 353 W Commonwealth Ave, Fullerton, CA 92832",
                        url=full_url,
                        description=description,
                        category="Educational",
                        source_url=url
                    )
                    events.append(event)
                except Exception as e:
                    logger.error(f"Error parsing library event: {e}")

            await browser.close()
        return events
