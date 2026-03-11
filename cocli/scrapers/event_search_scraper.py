import logging
import asyncio
import random
from datetime import datetime
from typing import List, Literal
from playwright.async_api import async_playwright, Page
from bs4 import BeautifulSoup

from ..models.campaigns.events import Event
from ..core.text_utils import slugify
from ..utils.playwright_utils import setup_stealth_context
from ..utils.headers import USER_AGENT
from ..utils.op_utils import get_op_secret
from ..models.campaigns.campaign import Campaign

logger = logging.getLogger(__name__)

class EventSearchScraper:
    def __init__(self, debug: bool = False):
        self.debug = debug

    async def search_and_extract(
        self, 
        query: str, 
        engine: Literal["google", "bing"] = "google",
        campaign_name: str = "fullertonian"
    ) -> List[Event]:
        """
        Performs a web search using the specified engine.
        """
        logger.info(f"Performing {engine} web search: {query}")
        
        async with async_playwright() as p:
            # Persist sessions in .playwright/
            from ..core.paths import paths
            user_data_dir = paths.root / ".playwright" / f"{engine}_session"
            user_data_dir.mkdir(parents=True, exist_ok=True)

            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                headless=not self.debug,
                user_agent=USER_AGENT,
                viewport={'width': 1920, 'height': 1080}
            )
            await setup_stealth_context(context)
            page = context.pages[0] if context.pages else await context.new_page()
            
            # 1. Ensure Login (if Google)
            if engine == "google":
                campaign = Campaign.load(campaign_name)
                await self._ensure_logged_in(page, campaign)

            # 2. Navigate to Search
            if engine == "google":
                url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
            else: # bing
                url = f"https://www.bing.com/search?q={query.replace(' ', '+')}"

            logger.info(f"Navigating to {engine} search: {url}")
            await page.goto(url)
            await page.wait_for_load_state("networkidle")
            
            # Wait for results
            try:
                selector = 'h3' if engine == "google" else 'h2'
                await page.wait_for_selector(selector, timeout=10000)
            except Exception:
                logger.warning(f"Timeout waiting for {engine} result headers.")

            html = await page.content()
            
            # Save raw data
            raw_dir = paths.campaign(campaign_name).raw / "events"
            raw_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%dT%H%M%S")
            raw_file = raw_dir / f"{ts}_{engine}_{slugify(query)}.html"
            raw_file.write_text(html)

            events = await self._heuristic_extract(html, query, engine)
            
            await context.close()
            return events

    async def _ensure_logged_in(self, page: Page, campaign: Campaign) -> None:
        """
        Checks if we are logged into Google, and performs login if not.
        """
        logger.info("Verifying Google login status...")
        await page.goto("https://accounts.google.com/")
        await page.wait_for_load_state("networkidle")

        content = await page.content()
        if "Sign in" not in content and ("Use another account" in content or "Google Account" in content):
            logger.info("Already logged into Google.")
            return

        logger.info("Starting robust Google login flow...")
        email = campaign.google_maps.email
        password = get_op_secret(campaign.google_maps.one_password_path)
        
        if not password:
            print("\n" + "!"*60)
            print("LOGIN ERROR: 1Password secret could not be retrieved.")
            print("Please run 'op signin' in your terminal.")
            print("OR: Log in manually in the browser window NOW.")
            print("!"*60 + "\n")
            await asyncio.sleep(10) # Give them a moment to read

        try:
            # Step 1: Email
            if await page.is_visible('input[type="email"]'):
                logger.info(f"Typing email character-by-character: {email}")
                await page.click('input[type="email"]')
                for char in email:
                    await page.type('input[type="email"]', char, delay=random.randint(100, 300))
                
                await asyncio.sleep(0.5)
                # Verification Check
                val = await page.input_value('input[type="email"]')
                if val != email:
                    logger.error(f"Email verification failed! Expected {email}, got {val}")
                    await page.fill('input[type="email"]', "")
                    await page.fill('input[type="email"]', email)
                
                # Human Mimicry: Brief pause and then ENTER
                await asyncio.sleep(random.uniform(0.5, 1.5))
                logger.info("Pressing ENTER to submit email...")
                await page.keyboard.press("Enter")
                
                logger.info("Waiting for password field...")
                await asyncio.sleep(random.uniform(3.0, 5.0))

            # Step 2: Password
            if password:
                await page.wait_for_selector('input[type="password"]', timeout=15000)
                await page.click('input[type="password"]')
                logger.info("Typing password...")
                for char in password:
                    await page.type('input[type="password"]', char, delay=random.randint(50, 200))
                
                # Human Mimicry: Move mouse to Password Next button
                pass_next = page.locator('#passwordNext')
                await pass_next.hover()
                await asyncio.sleep(random.uniform(0.5, 1.5))
                await pass_next.click()
                
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(5)
        except Exception as e:
            logger.warning(f"Automated login flow encountered an issue: {e}")
            logger.info("Waiting 2 minutes for manual login completion...")
            try:
                await page.wait_for_function("() => !document.body.innerText.includes('Sign in')", timeout=120000)
            except Exception:
                logger.error("Manual login timeout.")

    async def _heuristic_extract(self, html: str, query: str, engine: str) -> List[Event]:
        soup = BeautifulSoup(html, "html.parser")
        events = []
        
        if engine == "google":
            results = soup.select('div.g') or soup.select('div[class*="tF2Cxc"]')
        else: # bing
            results = soup.select('li.b_algo') or soup.select('article')

        if not results:
            headers = soup.find_all('h3') if engine == "google" else soup.find_all('h2')
            for h in headers:
                try:
                    name = h.get_text(strip=True)
                    if not name or len(name) < 10:
                        continue
                    link_elem = h.find_parent('a') or h.find_next('a')
                    url = link_elem.get('href') if link_elem else ""
                    if not url or any(k in str(url) for k in ["google.com", "bing.com", "microsoft.com"]):
                        continue
                    
                    events.append(Event(
                        start_time=datetime.now(),
                        host_slug=slugify(f"{engine} Result"),
                        event_slug=slugify(name),
                        name=name,
                        host_name="Web Source",
                        url=str(url),
                        category="Web Search",
                        source_url=f"{engine} query: {query}"
                    ))
                except Exception:
                    continue
            return events

        for res in results:
            try:
                title_elem = res.select_one('h3') if engine == "google" else res.select_one('h2')
                if not title_elem:
                    continue
                name = title_elem.get_text(strip=True)
                link_elem = res.select_one('a')
                url = link_elem.get('href') if link_elem else ""
                
                if any(k in name.lower() for k in ["guide", "best of", "top 10"]):
                    continue

                events.append(Event(
                    start_time=datetime.now(),
                    host_slug=slugify(f"{engine} Search"),
                    event_slug=slugify(name),
                    name=name,
                    host_name="External Source",
                    url=str(url) if url else None,
                    category="Web Search",
                    source_url=f"{engine} query: {query}"
                ))
            except Exception as e:
                logger.error(f"Error parsing search result: {e}")
        return events
