import re
import httpx
import asyncio
import xml.etree.ElementTree as ET
from typing import Optional, List, Callable, Coroutine, Any, Dict
from playwright.async_api import Page, Browser, BrowserContext
from bs4 import BeautifulSoup, Tag
import logging
from urllib.parse import urljoin
from datetime import datetime, timedelta

from ..models.website import Website
from ..core.website_domain_csv_manager import WebsiteDomainCsvManager
from ..models.website_domain_csv import WebsiteDomainCsv

logger = logging.getLogger(__name__)

CURRENT_SCRAPER_VERSION = 6

class WebsiteScraper:

    async def run(
        self,
        browser: Browser | BrowserContext, # Added browser argument
        domain: str,
        force_refresh: bool = False,
        ttl_days: int = 30,
        debug: bool = False
    ) -> Optional[Website]:
        if not domain:
            logger.info("No domain provided. Skipping website scraping.")
            return None

        index = WebsiteDomainCsvManager()
        fresh_delta = timedelta(days=ttl_days)

        # Check index first
        indexed_item = index.get_by_domain(domain)
        if indexed_item:
            is_stale = (datetime.utcnow() - indexed_item.updated_at) >= fresh_delta
            is_old_version = (indexed_item.scraper_version or 1) < CURRENT_SCRAPER_VERSION
            if not force_refresh and not is_stale and not is_old_version:
                logger.info(f"Using indexed data for {domain}, converting to Website model")
                # We have the indexed data, but the caller expects a full Website object.
                # We can create a Website object from the indexed data.
                return Website(**indexed_item.model_dump())
            if is_old_version:
                logger.info(f"Re-scraping {domain} due to new scraper version.")

        logger.info(f"Starting website scraping for {domain}")

        website_data = Website(url=domain, scraper_version=CURRENT_SCRAPER_VERSION)

        context: BrowserContext
        if isinstance(browser, Browser):
            context = await browser.new_context()
        else:
            context = browser

        page = await context.new_page()
        try:
            await page.goto(f"http://{domain}", wait_until="domcontentloaded", timeout=30000)

            if debug:
                breakpoint()

            # Scrape main page
            website_data = await self._scrape_page(page, website_data, context)

            # Try to find and scrape pages from sitemap
            sitemap_pages = await self._get_sitemap_urls(f"http://{domain}")
            if sitemap_pages:
                page_map = {
                    "About Us": ["about"],
                    "Contact Us": ["contact"],
                    "Services": ["service"],
                    "Products": ["product"],
                }
                scrape_tasks = []
                for page_type, keywords in page_map.items():
                    for keyword in keywords:
                        for url in sitemap_pages:
                            if keyword in url:
                                scrape_function = None
                                if page_type == "About Us":
                                    scrape_function = self._scrape_page
                                elif page_type == "Contact Us":
                                    scrape_function = self._scrape_contact_page
                                elif page_type == "Services":
                                    scrape_function = self._scrape_services_page
                                elif page_type == "Products":
                                    scrape_function = self._scrape_products_page

                                if scrape_function:
                                    scrape_tasks.append(self._scrape_sitemap_page(url, page_type, scrape_function, website_data, context, debug))
                                    break
                        else:
                            continue
                        break
                if scrape_tasks:
                    await asyncio.gather(*scrape_tasks)

            # Fallback to navigating and scraping
            if not website_data.about_us_url:
                await self._navigate_and_scrape(page, website_data, ["About Us", "About"], "About Us", self._scrape_page, context, debug)
            if not website_data.contact_url:
                await self._navigate_and_scrape(page, website_data, ["Contact Us", "Contact"], "Contact Us", self._scrape_contact_page, context, debug)
            if not website_data.services:
                await self._navigate_and_scrape(page, website_data, ["Services"], "Services", self._scrape_services_page, context, debug)
            if not website_data.products:
                await self._navigate_and_scrape(page, website_data, ["Products"], "Products", self._scrape_products_page, context, debug)

        except Exception as e:
            logger.error(f"Error during website scraping for {domain}: {e}")
            return None
        finally:
            await page.close()
            if isinstance(browser, Browser):
                await context.close()

        # Add to index
        website_domain_csv_data = WebsiteDomainCsv(
            domain=str(website_data.domain),
            company_name=website_data.company_name,
            phone=website_data.phone,
            email=website_data.email,
            facebook_url=website_data.facebook_url,
            linkedin_url=website_data.linkedin_url,
            instagram_url=website_data.instagram_url,
            twitter_url=website_data.twitter_url,
            youtube_url=website_data.youtube_url,
            address=website_data.address,
            personnel=[p.get("name", "") for p in website_data.personnel] if website_data.personnel else [],

            about_us_url=website_data.about_us_url,
            contact_url=website_data.contact_url,
            services_url=website_data.services_url,
            products_url=website_data.products_url,
            tags=website_data.tags,
            scraper_version=website_data.scraper_version,
            associated_company_folder=website_data.associated_company_folder,
            is_email_provider=website_data.is_email_provider,
            created_at=website_data.created_at,
            updated_at=website_data.updated_at,
        )
        index.add_or_update(website_domain_csv_data)

        return website_data

    async def _scrape_sitemap_page(self, url: str, page_type: str, scrape_function: Callable[[Page, Website, BrowserContext], Coroutine[Any, Any, Website]], website_data: Website, browser: BrowserContext, debug: bool) -> None:
        try:
            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await scrape_function(page, website_data, browser)
            await page.close()
        except Exception as e:
            logger.warning(f"Failed to scrape {page_type} page from sitemap: {e}")

    async def _get_sitemap_urls(self, domain: str) -> List[str]:
        sitemap_url = urljoin(str(domain), "/sitemap.xml")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(sitemap_url, timeout=5)
                if response.status_code == 200:
                    root = ET.fromstring(response.content)
                    urls = []
                    for elem in root.iter():
                        if 'url' in elem.tag:
                            for loc in elem.iter():
                                if 'loc' in loc.tag and loc.text is not None:
                                    urls.append(loc.text)
                    logger.info(f"Found {len(urls)} URLs in sitemap for {domain}")
                    return urls
        except Exception as e:
            logger.info(f"Could not fetch or parse sitemap for {domain}: {e}")
        return []

    async def _scrape_services_page(self, page: Page, website_data: Website, browser: BrowserContext) -> Website:
        html_content = await page.content()
        soup = BeautifulSoup(html_content, "html.parser")

        services = []
        service_selectors = ["[id*=service]", "[class*=service]", "[id*=offering]", "[class*=offering]", "[id*=feature]", "[class*=feature]"]
        service_sections: List[Tag] = soup.select(", ".join(service_selectors))

        if not service_sections:
            # If no specific sections are found, fall back to the old method
            service_sections = [soup]

        for section in service_sections:
            # Look for list items or headings that might contain service names
            service_elements = section.select('li, h2, h3, h4, p')
            for element in service_elements:
                text = element.get_text(strip=True)
                # Filter out short or irrelevant text and duplicates
                if 3 < len(text) < 100 and text not in services:
                    services.append(text)

        website_data.services = services
        logger.info(f"Found {len(website_data.services)} potential services on {page.url}")
        return website_data

    async def _scrape_products_page(self, page: Page, website_data: Website, browser: BrowserContext) -> Website:
        html_content = await page.content()
        soup = BeautifulSoup(html_content, "html.parser")

        products = []
        product_selectors = ["[id*=product]", "[class*=product]", "[id*=portfolio]", "[class*=portfolio]", "[id*=gallery]", "[class*=gallery]"]
        product_sections: List[Tag] = soup.select(", ".join(product_selectors))

        if not product_sections:
            # If no specific sections are found, fall back to the old method
            product_sections = [soup]

        for section in product_sections:
            # Look for list items or headings that might contain product names
            product_elements = section.select('li, h2, h3, h4, p')
            for element in product_elements:
                text = element.get_text(strip=True)
                # Filter out short or irrelevant text and duplicates
                if 3 < len(text) < 100 and text not in products:
                    products.append(text)

        website_data.products = products
        logger.info(f"Found {len(website_data.products)} potential products on {page.url}")
        return website_data

    async def _navigate_and_scrape(self, page: Page, website_data: Website, link_texts: List[str], page_type: str, scrape_function: Callable[..., Coroutine[Any, Any, Website]], browser: BrowserContext, debug: bool) -> Website:
        # Use a case-insensitive regex for link text
        link_selector = ", ".join([f'a:text-matches("{text}", "i")' for text in link_texts])
        link = page.locator(link_selector).first

        try:
            if not await link.is_visible(timeout=1000):
                logger.info(f"Link for {page_type} not immediately visible, trying to find a hoverable parent.")
                # A common pattern is that the `li` containing the `a` is the hover target
                hover_target = link.locator('xpath=..')
                if hover_target:
                    await hover_target.hover(timeout=1000)
        except Exception:
            logger.info(f"Could not hover to find link for {page_type}. Will try to proceed anyway.")

        try:
            url = await link.get_attribute("href", timeout=1000)
            if url:
                url = urljoin(page.url, url)
                if url and url != page.url:
                    logger.info(f"Navigating to {page_type} page: {url}")
                    if page_type == "About Us":
                        website_data.about_us_url = url
                    elif page_type == "Contact Us":
                        website_data.contact_url = url
                    elif page_type == "Services":
                        website_data.services_url = url
                    elif page_type == "Products":
                        website_data.products_url = url

                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    await scrape_function(page, website_data, browser)
        except Exception as e:
            logger.error(f"Error navigating to or scraping {page_type} page: {e}")
        return website_data

    async def _scrape_page(self, page: Page, website_data: Website, browser: BrowserContext) -> Website:
        html_content = await page.content()
        soup = BeautifulSoup(html_content, "html.parser")

        # Extract Company Name
        if not website_data.company_name:
            company_name = None
            if soup.title and soup.title.string:
                company_name = soup.title.string.split('|')[0].split('-')[0].strip()
            if not company_name or len(company_name) < 3:
                h1 = soup.find('h1')
                if h1 and h1.string:
                    company_name = h1.string.strip()
            if not company_name or len(company_name) < 3:
                logo = soup.select_one('[class*=logo], [id*=logo]')
                if logo and logo.text:
                    company_name = logo.text.strip()
            if company_name and len(company_name) > 2:
                website_data.company_name = company_name
                logger.info(f"Found company name: {company_name}")

        # Extract Phone Number
        if not website_data.phone:
            phone_match = re.search(r"\b(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})\b", soup.get_text(separator=' '))
            if phone_match:
                website_data.phone = str(phone_match.group(0))
                logger.info(f"Found phone number: {website_data.phone}")

        # Extract Email
        if not website_data.email:
            email_match = re.search(r"\b[a-zA-Z0-9._%+-]+ ?@ ?[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b", soup.get_text(separator=' '))
            if email_match:
                website_data.email = str(email_match.group(0)).replace(" ", "")
                logger.info(f"Found email: {website_data.email}")

        # Extract Social Media URLs
        if not website_data.facebook_url:
            facebook_link = soup.find("a", href=re.compile(r"facebook\.com", re.IGNORECASE))
            if facebook_link:
                website_data.facebook_url = str(facebook_link["href"])
                logger.info(f"Found Facebook URL: {website_data.facebook_url}")

        if not website_data.linkedin_url:
            linkedin_link = soup.find("a", href=re.compile(r"linkedin\.com", re.IGNORECASE))
            if linkedin_link:
                website_data.linkedin_url = str(linkedin_link["href"])
                logger.info(f"Found LinkedIn URL: {website_data.linkedin_url}")

        if not website_data.instagram_url:
            instagram_link = soup.find("a", href=re.compile(r"instagram\.com", re.IGNORECASE))
            if instagram_link:
                website_data.instagram_url = str(instagram_link["href"])
                logger.info(f"Found Instagram URL: {website_data.instagram_url}")

        if not website_data.twitter_url:
            twitter_link = soup.find("a", href=re.compile(r"twitter\.com", re.IGNORECASE))
            if twitter_link:
                website_data.twitter_url = str(twitter_link["href"])
                logger.info(f"Found Twitter URL: {website_data.twitter_url}")

        if not website_data.youtube_url:
            youtube_link = soup.find("a", href=re.compile(r"youtube\.com", re.IGNORECASE))
            if youtube_link:
                website_data.youtube_url = str(youtube_link["href"])
                logger.info(f"Found Youtube URL: {website_data.youtube_url}")

        # Extract Address
        if not website_data.address:
            # A simple regex for US addresses
            address_match = re.search(r"\d+\s+([a-zA-Z]+\s+)+[a-zA-Z]+,?\s+[A-Z]{2}\s+\d{5}", soup.get_text(separator=' '))
            if address_match:
                website_data.address = str(address_match.group(0))
                logger.info(f"Found address: {website_data.address}")

        # Extract Description
        if page.url == website_data.about_us_url:
            main_content = soup.select_one('main, article, #main, #content, .main, .content')
            if main_content:
                # Remove nav and footer from main content if they exist
                for tag in main_content.select('nav, footer'):
                    tag.decompose()
                website_data.description = str(main_content.get_text(separator='\n', strip=True))
            else:
                # Fallback to body if no main content found
                if soup.body:
                    for tag in soup.body.select('nav, footer, header'):
                        tag.decompose()
                    website_data.description = str(soup.body.get_text(separator='\n', strip=True))
            logger.info(f"Found description for {website_data.domain} from About Us page")
        elif not website_data.description:
            # Fallback for other pages if description not already found
            about_section = soup.find(id=re.compile("about", re.IGNORECASE)) or soup.find(class_=re.compile("about", re.IGNORECASE))
            if about_section:
                website_data.description = str(about_section.get_text(separator='\n', strip=True))
                logger.info(f"Found description for {website_data.domain}")

        return website_data

    async def _scrape_contact_page(self, page: Page, website_data: Website, browser: BrowserContext) -> Website:
        await self._scrape_page(page, website_data, browser)
        # Now, look for more specific contact info
        html_content = await page.content()
        soup = BeautifulSoup(html_content, "html.parser")

        # Example: find email addresses with roles
        email_matches = re.findall(r"(\w+\s*:\s*[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", soup.get_text(separator=' '))
        for match in email_matches:
            website_data.personnel.append(match)

        # Look for personnel links
        personnel_selectors = [".member__wrapper", ".person__card", ".team__member", ".staff__item"]
        personnel_elements = soup.select(", ".join(personnel_selectors))

        for element in personnel_elements:
            link = element.find("a", href=True)
            if link and link["href"]:
                person_url = urljoin(str(page.url), str(link["href"]))
                if person_url and person_url != page.url:
                    logger.info(f"Navigating to personnel page: {person_url}")
                    person_page = await browser.new_page()
                    try:
                        await person_page.goto(person_url, wait_until="domcontentloaded", timeout=30000)
                        person_data = await self._scrape_personnel_details(person_page, website_data)
                        if person_data:
                            website_data.personnel.append(person_data)
                    except Exception as e:
                        logger.warning(f"Failed to scrape personnel page {person_url}: {e}")
                    finally:
                        await person_page.close()
        return website_data

    async def _scrape_personnel_details(self, page: Page, website_data: Website) -> Optional[Dict[str, Any]]:
        html_content = await page.content()
        soup = BeautifulSoup(html_content, "html.parser")

        person_data: Dict[str, Any] = {}

        # Extract Name and Title
        name_element = soup.select_one("h1, .member__name, .person__name")
        if name_element is not None:
            person_data["name"] = name_element.get_text(strip=True)
            logger.info(f"Found person name: {person_data['name']}")

        title_element = soup.select_one(".member__position, .person__position, .person__title")
        if title_element is not None:
            person_data["title"] = title_element.get_text(strip=True)
            logger.info(f"Found person title: {person_data['title']}")

        # Extract Email
        email_match = re.search(r"\b[a-zA-Z0-9._%+-]+ ?@ ?[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b", soup.get_text(separator=' '))
        if email_match:
            person_data["email"] = email_match.group(0).replace(" ", "")
            logger.info(f"Found person email: {person_data['email']}")

        # Extract LinkedIn URL
        linkedin_link = soup.find("a", href=re.compile(r"linkedin\.com/in/", re.IGNORECASE))
        if linkedin_link:
            person_data["linkedin_url"] = str(linkedin_link["href"])
            logger.info(f"Found person LinkedIn URL: {person_data['linkedin_url']}")

        # Extract Phone Number
        phone_match = re.search(r"\b(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})\b", soup.get_text(separator=' '))
        if phone_match:
            person_data["phone"] = str(phone_match.group(0))
            logger.info(f"Found person phone: {person_data['phone']}")

        if person_data:
            return person_data
        return None
