import asyncio
import logging
import aiohttp
from typing import Optional, Tuple
from selectolax.lexbor import LexborHTMLParser

logger = logging.getLogger(__name__)

class HeadScraper:
    """
    A high-speed streaming scraper that only fetches the <head> of a website.
    Stops downloading as soon as </head> is found.
    """
    def __init__(self, timeout_seconds: int = 10):
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

    async def fetch_head(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Fetches the <head> section of the URL.
        Returns (head_html, title).
        """
        if not url.startswith("http"):
            url = f"https://{url}"

        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url, timeout=self.timeout, allow_redirects=True) as response:
                    if response.status != 200:
                        return None, None

                    chunks = []
                    
                    # Stream the response
                    async for chunk in response.content.iter_any():
                        chunk_str = chunk.decode("utf-8", errors="ignore")
                        chunks.append(chunk_str)
                        
                        if "</head>" in chunk_str.lower():
                            response.close() # Terminate the connection early
                            break
                        
                        # Safety limit: if we've read more than 100KB and haven't found </head>, stop.
                        if sum(len(c) for c in chunks) > 102400:
                            break

                    full_content = "".join(chunks)
                    parser = LexborHTMLParser(full_content)
                    
                    head_node = parser.css_first("head")
                    head_html: Optional[str] = None
                    if not head_node:
                        # Fallback: maybe it's malformed and doesn't have a <head> tag
                        head_html = full_content.split("<body>")[0] if "<body>" in full_content.lower() else full_content
                    else:
                        head_html = head_node.html

                    title_node = parser.css_first("title")
                    title: Optional[str] = title_node.text().strip() if title_node else None
                    
                    return head_html, title

        except Exception as e:
            logger.debug(f"HeadScraper error for {url}: {e}")
            return None, None

async def main() -> None:
    scraper = HeadScraper()
    url = "https://beckerarena.com"
    head, title = await scraper.fetch_head(url)
    print(f"Title: {title}")
    if head:
        print(f"Head size: {len(head)} bytes")

if __name__ == "__main__":
    asyncio.run(main())
