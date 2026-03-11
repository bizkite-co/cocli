import logging
import asyncio
from datetime import datetime
from typing import List
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

from ..models.campaigns.events import Event
from ..core.text_utils import slugify
from ..utils.playwright_utils import setup_stealth_context
from ..utils.headers import USER_AGENT

logger = logging.getLogger(__name__)

class EventSearchScraper:
    def __init__(self, debug: bool = False):
        self.debug = debug

    async def search_and_extract(self, query: str, campaign_name: str = "fullertonian") -> List[Event]:
        """
        Performs a web search and uses LLM-style extraction to find events.
        """
        logger.info(f"Performing web search: {query}")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=not self.debug)
            
            # Apply standard project stealth settings
            context = await browser.new_context(user_agent=USER_AGENT)
            await setup_stealth_context(context)
            
            page = await context.new_page()
            
            # Simple Google search implementation
            search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
            await page.goto(search_url)
            await page.wait_for_load_state("networkidle")
            
            # Additional sleep to ensure dynamic content is ready
            await asyncio.sleep(5)
            
            # Simple interaction to look more human
            await page.mouse.move(100, 100)
            await asyncio.sleep(1)
            
            html = await page.content()
            
            # --- RAW DATA STORAGE ---
            from ..core.paths import paths
            from datetime import datetime
            raw_dir = paths.campaign(campaign_name).raw / "events"
            raw_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%dT%H%M%S")
            raw_file = raw_dir / f"{ts}_{slugify(query)}.html"
            raw_file.write_text(html)
            logger.info(f"Saved raw HTML to: {raw_file}")

            # --- BOT DETECTION ---
            bot_keywords = ["suspicious activity", "unusual traffic", "captcha", "prove you're not a robot", "detected suspicious"]
            page_text = await page.evaluate("() => document.body.innerText")
            if any(k in page_text.lower() for k in bot_keywords):
                logger.error(f"BOT DETECTION TRIGGERED for query: {query}")
                # We still try to extract what we can, but log the failure
                if self.debug:
                    print(f"BOT DETECTION TEXT FOUND: {page_text[:200]}...")

            # In a full implementation, we'd pass this HTML to an LLM.
            # For this prototype, we'll use a heuristic to find result blocks
            # and extract potential event data.
            events = await self._heuristic_llm_extract(html, query)
            
            await browser.close()
            return events

    async def _heuristic_llm_extract(self, html: str, query: str) -> List[Event]:
        """
        Simulates an LLM extraction by looking for common result patterns.
        """
        soup = BeautifulSoup(html, "html.parser")
        events = []
        
        # Extremely generic fallbacks
        results = soup.select('div.g') or \
                  soup.select('div[class*="tF2Cxc"]') or \
                  soup.select('div.MjjYud') or \
                  soup.find_all(['div', 'section'], recursive=False)
        
        # If we still have nothing, we just look for all h3s
        if not results or len(results) < 5:
            results = soup.find_all('h3')
            logger.info(f"Using H3-only fallback. Found {len(results)} H3s.")
            for h3 in results:
                try:
                    name = h3.get_text(strip=True)
                    parent = h3.find_parent(['div', 'a'])
                    link_elem = parent.find('a', href=True) if parent else h3.find_next('a', href=True)
                    url = link_elem.get('href') if link_elem else ""
                    
                    if not name or not url or "google.com" in str(url):
                        continue

                    event = Event(
                        start_time=datetime.now(),
                        host_slug=slugify("Web Search"),
                        event_slug=slugify(name),
                        name=name,
                        host_name="Web Source",
                        url=str(url),
                        category="Web Search",
                        source_url=f"Search Query: {query}"
                    )
                    events.append(event)
                except Exception:
                    continue
            return events

        logger.info(f"Found {len(results)} potential result blocks.")

        for res in results:
            try:
                title_elem = res.select_one('h3')
                if not title_elem:
                    continue
                
                name = title_elem.get_text(strip=True)
                link_elem = res.select_one('a')
                url = link_elem.get('href') if link_elem else ""
                
                # Snippet text often contains date info
                snippet_elem = res.select_one('div[style*="-webkit-line-clamp"]') or res.select_one('.VwiC3b')
                snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""

                # We skip obviously non-event results (like generic guides or news homepages)
                if any(k in name.lower() for k in ["guide", "best of", "top 10", "how to"]):
                    continue

                event = Event(
                    start_time=datetime.now(), # Placeholder until LLM parses snippet
                    host_slug=slugify("Web Search Result"),
                    event_slug=slugify(name),
                    name=name,
                    host_name="External Source",
                    url=url if isinstance(url, str) else None,
                    description=snippet,
                    category="Web Search",
                    source_url=f"Search Query: {query}"
                )
                events.append(event)
            except Exception as e:
                logger.error(f"Error parsing search result: {e}")

        return events
