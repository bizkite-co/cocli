import asyncio
from typing import Optional, Any
from playwright.async_api import async_playwright, Browser, Page


class BrowserManager:
    """Manages a persistent Chrome browser instance for auditing."""

    def __init__(self) -> None:
        self.playwright: Any = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self._lock = asyncio.Lock()

    async def _ensure_browser(self) -> Browser:
        if self.browser is None:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=False, args=["--start-maximized"]
            )
        return self.browser

    async def open_url(self, url: str) -> None:
        async with self._lock:
            browser = await self._ensure_browser()
            if self.page is None or self.page.is_closed():
                self.page = await browser.new_page()
            await self.page.goto(url)
            await self.page.bring_to_front()

    async def close(self) -> None:
        async with self._lock:
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            self.browser = None
            self.playwright = None
            self.page = None
