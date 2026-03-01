# POLICY: frictionless-data-policy-enforcement
import logging
import asyncio
from typing import Optional
from datetime import datetime, UTC
from playwright.async_api import Page
from transitions.extensions.asyncio import AsyncMachine

from cocli.models.campaigns.raw_witness import RawWitness

logger = logging.getLogger(__name__)

class GoogleMapsDetailsScraper:
    """
    A state-machine driven scraper for Google Maps details.
    Ensures high-fidelity capture through verified warmup and hydration steps.
    
    Contract: PlaceID -> [Warmup -> Navigate -> Heal -> Capture] -> RawWitness
    """
    
    # State Definitions
    states = [
        'initialized', 
        'warming_up',   # Navigating to google.com/maps to establish cookies
        'navigating',   # Moving to the specific Place ID URL
        'hydrating',    # Performing 'Session-Heal' clicks to reveal full data
        'capturing',    # Extracting the final hydrated HTML and metadata
        'completed',    # terminal: success
        'failed'        # terminal: error
    ]

    def __init__(self, page: Page, campaign_name: str, processed_by: str = "local-scraper"):
        self.page = page
        self.campaign_name = campaign_name
        self.processed_by = processed_by
        
        # Internal State
        self.place_id: Optional[str] = None
        self.witness: Optional[RawWitness] = None
        self.error: Optional[str] = None
        self.start_time: Optional[datetime] = None
        
        # Initialize Async Machine
        self.machine = AsyncMachine(
            model=self, 
            states=GoogleMapsDetailsScraper.states, 
            initial='initialized'
        )
        
        # Define Transitions
        # Trigger | Source | Destination
        self.machine.add_transition('start_warmup', 'initialized', 'warming_up')
        self.machine.add_transition('proceed_to_navigate', 'warming_up', 'navigating')
        self.machine.add_transition('proceed_to_hydrate', 'navigating', 'hydrating')
        self.machine.add_transition('proceed_to_capture', 'hydrating', 'capturing')
        self.machine.add_transition('finalize', 'capturing', 'completed')
        self.machine.add_transition('fail', '*', 'failed')

    async def scrape(self, place_id: str) -> Optional[RawWitness]:
        """
        Main entry point. Executes the state machine for a specific Place ID.
        """
        self.place_id = place_id
        self.witness = None
        self.error = None
        self.start_time = datetime.now(UTC)
        
        logger.info(f"[{place_id}] Starting State Machine Scrape...")
        
        try:
            # 1. Warmup
            await self.start_warmup() # type: ignore
            
            # 2. Navigate
            await self.proceed_to_navigate() # type: ignore
            
            # 3. Hydrate
            await self.proceed_to_hydrate() # type: ignore
            
            # 4. Capture
            await self.proceed_to_capture() # type: ignore
            
            # 5. Complete
            await self.finalize() # type: ignore
            
            duration = (datetime.now(UTC) - self.start_time).total_seconds() if self.start_time else 0
            logger.info(f"[{place_id}] Scrape Completed successfully in {duration:.2f}s")
            return self.witness
            
        except Exception as e:
            self.error = str(e)
            logger.error(f"[{place_id}] Scraper failed in state '{self.state}': {e}") # type: ignore
            if self.state != 'failed': # type: ignore
                await self.fail() # type: ignore
            return None

    # --- State Callbacks ---

    async def on_enter_warming_up(self) -> None:
        """Action: Ensure we have a session established."""
        # Use existing logic: establishing session state to avoid 'Limited View'
        if not self.page.url.startswith("https://www.google.com/maps"):
            logger.debug(f"[{self.place_id}] WARMUP: Navigating to google.com/maps...")
            await self.page.goto("https://www.google.com/maps", wait_until="commit", timeout=30000)
            await asyncio.sleep(2)

    async def on_enter_navigating(self) -> None:
        """Action: Navigate to the target Place ID."""
        url = f"https://www.google.com/maps/place/?q=place_id:{self.place_id}"
        logger.debug(f"[{self.place_id}] NAVIGATING: {url}")
        await self.page.goto(url, wait_until="load", timeout=60000)
        # Wait for the sidebar content area
        await self.page.wait_for_selector('h1, div[role="main"], .qBF1Pd', timeout=30000)
        await asyncio.sleep(5) # Let dynamic elements settle

    async def on_enter_hydrating(self) -> None:
        """Action: Trigger hydration clicks (Session-Heal)."""
        logger.debug(f"[{self.place_id}] HYDRATING: Searching for triggers...")
        hydration_triggers = [
            'div[jsaction*="reviewChart.moreReviews"]',
            'button[jsaction*="pane.rating.moreReviews"]',
            'div[jsaction*="pane.rating.moreReviews"]',
            'span[aria-label*="stars"]',
            'button[aria-label*="reviews"]'
        ]
        
        for selector in hydration_triggers:
            try:
                el = await self.page.wait_for_selector(selector, timeout=5000)
                if el:
                    logger.debug(f"[{self.place_id}] HYDRATING: Clicking {selector}")
                    await el.click()
                    await asyncio.sleep(5) # Wait for full review data to load
                    break
            except Exception:
                continue

    async def on_enter_capturing(self) -> None:
        """Action: Capture and package the raw witness."""
        logger.debug(f"[{self.place_id}] CAPTURING HTML...")
        html_content = await self.page.content()
        
        if self.place_id:
            self.witness = RawWitness(
                place_id=self.place_id,
                processed_by=self.processed_by,
                campaign_name=self.campaign_name,
                url=self.page.url,
                html=html_content,
                metadata={
                    "strategy": "state-machine-v1",
                    "final_state": self.state, # type: ignore
                    "viewport": str(self.page.viewport_size),
                    "duration_seconds": (datetime.now(UTC) - self.start_time).total_seconds() if self.start_time else 0
                }
            )
