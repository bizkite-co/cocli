import re
import httpx
import asyncio
import xml.etree.ElementTree as ET
from typing import Optional, List, Callable, Coroutine, Any, Dict, Union
from playwright.async_api import Page, Browser, BrowserContext
from bs4 import BeautifulSoup, Tag
import logging
from urllib.parse import urljoin
from datetime import datetime, timedelta

from ..models.website import Website
from ..core.website_domain_csv_manager import WebsiteDomainCsvManager, CURRENT_SCRAPER_VERSION
from ..core.s3_domain_manager import S3DomainManager
from ..core.s3_company_manager import S3CompanyManager
from ..models.website_domain_csv import WebsiteDomainCsv
from ..models.campaign import Campaign
from ..core.exceptions import NavigationError, EnrichmentError
from ..core.email_index_manager import EmailIndexManager
from ..models.email import EmailEntry

logger = logging.getLogger(__name__)

class WebsiteScraper:

    def _index_emails(self, website_data: Website, campaign_name: str) -> None:
        """Helper to record all found emails in the centralized email index."""
        if not website_data.url:
            return

        index_manager = EmailIndexManager(campaign_name)
        
        # 1. All found emails
        for email in website_data.all_emails:
            entry = EmailEntry(
                email=email,
                domain=str(website_data.url),
                company_slug=website_data.associated_company_folder,
                source="website_scraper",
                tags=website_data.tags
            )
            index_manager.add_email(entry)

        # 2. Personnel emails
        if website_data.personnel:
            for person in website_data.personnel:
                person_email = person.get("email")
                if person_email and isinstance(person_email, str):
                    entry = EmailEntry(
                        email=person_email,
                        domain=str(website_data.url),
                        company_slug=website_data.associated_company_folder,
                        source="website_scraper_personnel",
                        tags=website_data.tags
                    )
                    # Add person name/title to tags or metadata if we had more fields
                    if person.get("name"):
                        entry.tags.append(f"person:{person['name']}")
                    index_manager.add_email(entry)

    async def _resolve_canonical_url(self, domain: str) -> Optional[str]:
        """Rapidly find the working URL for a domain, following redirects."""
        import httpx
        # Match wget behavior: try http first for legacy domain redirects
        protocols = ["http://", "https://"]
        for protocol in protocols:
            url = f"{protocol}{domain}"
            try:
                async with httpx.AsyncClient(follow_redirects=True, verify=False) as client:
                    response = await client.get(url, timeout=10.0)
                    if response.status_code == 200:
                        return str(response.url)
            except Exception:
                continue
        return None

    async def run(
        self,
        browser: Union[Browser, BrowserContext],
        domain: str,
        force_refresh: bool = False,
        ttl_days: int = 30,
        debug: bool = False,
        campaign: Optional[Campaign] = None,
        navigation_timeout_ms: int = 30000
    ) -> Website:
        """
        Scrapes a website for company information.
        """
        # S3DomainManager is used for the scrape index (lat/lon bounds), not for individual website.md files
        domain_index_manager: Union[WebsiteDomainCsvManager, S3DomainManager]
        if campaign and campaign.aws and campaign.aws.profile:
            domain_index_manager = S3DomainManager(campaign=campaign)
        else:
            domain_index_manager = WebsiteDomainCsvManager()
            domain_index_manager = WebsiteDomainCsvManager() # Fallback to local
        
        # S3CompanyManager is for saving the actual website.md and _index.md files
        s3_company_manager: Optional[S3CompanyManager] = None
        # In Fargate, we might not have a profile, but we have IAM roles.
        # We should try to init S3CompanyManager if we have a campaign context.
        if campaign:
            try:
                s3_company_manager = S3CompanyManager(campaign=campaign)
            except Exception as e:
                logger.warning(f"Could not initialize S3CompanyManager: {e}")


        fresh_delta = timedelta(days=ttl_days)

        # Check domain index first (using S3DomainManager or local CSV)
        indexed_item = domain_index_manager.get_by_domain(domain)
        if indexed_item:
            is_stale = (datetime.utcnow() - indexed_item.updated_at) >= fresh_delta
            is_old_version = (indexed_item.scraper_version or 1) < CURRENT_SCRAPER_VERSION
            if not force_refresh and not is_stale and not is_old_version:
                logger.info(f"Using indexed data for {domain}, converting to Website model")
                data = indexed_item.model_dump()
                # Clean up personnel if it contains empty strings or non-dict items
                if 'personnel' in data and isinstance(data['personnel'], list):
                    data['personnel'] = [p for p in data['personnel'] if isinstance(p, dict)]
                return Website(**data)
            if is_old_version:
                logger.info(f"Re-scraping {domain} due to new scraper version.")

        logger.info(f"Starting website scraping for {domain}")

        website_data = Website(url=domain, scraper_version=CURRENT_SCRAPER_VERSION)

        context: BrowserContext
        if isinstance(browser, Browser):
            context = await browser.new_context(ignore_https_errors=True, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        else:
            context = browser

        page = await context.new_page()
        try:
            # 1. Resolve canonical URL (rapidly handle redirects/broken protocols)
            canonical_url = await self._resolve_canonical_url(domain)
            if not canonical_url:
                # Fallback to simple protocol logic if httpx probe failed
                canonical_url = f"https://{domain}"
            
            logger.info(f"Resolved canonical URL for {domain}: {canonical_url}")
            
            # 2. Navigate with Playwright
            try:
                # Use load (wait for all assets) instead of networkidle to avoid timeouts from tracking pixels
                response = await page.goto(canonical_url, wait_until="load", timeout=navigation_timeout_ms)
                if not response or not response.ok:
                    status = response.status if response else "No Response"
                    raise Exception(f"Navigation failed with status {status}")
                
                website_data.url = page.url
                logger.info(f"Successfully navigated to {page.url}")
            except Exception as e:
                logger.warning(f"Playwright navigation failed to {canonical_url}: {e}")
                # Last resort fallback logic here if needed
                raise Exception(f"Could not navigate to {domain}. Error: {e}")

            # Update the domain if it changed significantly via redirect
            from urllib.parse import urlparse
            final_domain = urlparse(page.url).netloc.replace("www.", "")
            if final_domain and final_domain != domain.replace("www.", ""):
                logger.info(f"Detected redirect from {domain} to {final_domain}")
                # We keep the original domain in website_data.domain for indexing purposes if it was passed,
                # but we should probably record the final one too.



            if debug:
                breakpoint()

            # Scrape main page
            website_data = await self._scrape_page(page, website_data, context)

            if website_data.email:
                logger.info(f"Found primary email on home page: {website_data.email}. Skipping deep crawl fallbacks.")
            else:
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

                # Fallback to navigating and scraping (only if still no email or URLs)
                if not website_data.about_us_url:
                    await self._navigate_and_scrape(page, website_data, ["About", "About Us", "Our Story", "Company"], "About Us", self._scrape_page, context, debug, navigation_timeout_ms)
                if not website_data.contact_url:
                    await self._navigate_and_scrape(page, website_data, ["Contact", "Contacts", "Contact Us", "Get in Touch", "Reach Us"], "Contact Us", self._scrape_contact_page, context, debug, navigation_timeout_ms)
                if not website_data.contact_url:
                    await self._navigate_and_scrape(page, website_data, ["Our Team", "Team"], "Our Team", self._scrape_contact_page, context, debug, navigation_timeout_ms)
                if not website_data.services:
                    await self._navigate_and_scrape(page, website_data, ["Services"], "Services", self._scrape_services_page, context, debug, navigation_timeout_ms)
                if not website_data.products:
                    await self._navigate_and_scrape(page, website_data, ["Products"], "Products", self._scrape_products_page, context, debug, navigation_timeout_ms)

        except NavigationError:
            raise # Re-raise NavigationError
        except Exception as e:
            error_msg = f"Error during website scraping for {domain}. Type: {type(e).__name__}, Message: {e}"
            logger.error(error_msg, exc_info=True) # Log full traceback to CloudWatch
            raise EnrichmentError(error_msg) from e # Chain the exception
        finally:
            await page.close()
            if isinstance(browser, Browser):
                await context.close()

        # Save canonical website.md to S3 (if S3CompanyManager is active)
        if s3_company_manager and website_data.domain and campaign.company_slug: # type: ignore
             await s3_company_manager.save_website_enrichment(campaign.company_slug, website_data) # type: ignore
             logger.info(f"Saved canonical website.md for {domain} to S3.")

        # Add to domain index (for cache checking)
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
            all_emails=website_data.all_emails,
            email_contexts=website_data.email_contexts,
            tech_stack=website_data.tech_stack,
            created_at=website_data.created_at,
            updated_at=datetime.utcnow(), # Ensure updated_at is always current
        )
        domain_index_manager.add_or_update(website_domain_csv_data)

        # Index found emails for yield tracking
        if campaign:
            self._index_emails(website_data, campaign.name)

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
        sitemap_locations = ["/sitemap.xml", "/sitemap_index.xml", "/sitemap.desktop.xml"]
        all_urls = set()
        
        async with httpx.AsyncClient(follow_redirects=True) as client:
            for loc in sitemap_locations:
                sitemap_url = urljoin(str(domain), loc)
                try:
                    response = await client.get(sitemap_url, timeout=5)
                    if response.status_code == 200:
                        root = ET.fromstring(response.content)
                        # Check for sitemapindex
                        if 'sitemapindex' in root.tag:
                            for sm in root.iter():
                                if 'loc' in sm.tag and sm.text:
                                    # Fetch sub-sitemap
                                    try:
                                        sub_resp = await client.get(sm.text, timeout=5)
                                        if sub_resp.status_code == 200:
                                            sub_root = ET.fromstring(sub_resp.content)
                                            for elem in sub_root.iter():
                                                if 'loc' in elem.tag and elem.text:
                                                    all_urls.add(elem.text)
                                    except Exception:
                                        continue
                        else:
                            for elem in root.iter():
                                if 'loc' in elem.tag and elem.text:
                                    all_urls.add(elem.text)
                except Exception as e:
                    logger.debug(f"Could not fetch/parse sitemap at {sitemap_url}: {e}")
                    
        if all_urls:
            logger.info(f"Found {len(all_urls)} total URLs in sitemaps for {domain}")
        return list(all_urls)

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

    async def _navigate_and_scrape(self, page: Page, website_data: Website, link_texts: List[str], page_type: str, scrape_function: Callable[..., Coroutine[Any, Any, Website]], browser: BrowserContext, debug: bool, navigation_timeout_ms: Optional[int]) -> Website:
        # Use a case-insensitive regex for link text
        link_selector = ", ".join([f'a:text-matches("{text}", "i")' for text in link_texts])
        link = page.locator(link_selector).first

        # IMPORTANT: We only want to wait a VERY short time to see if the link exists at all.
        # If it's not there, we shouldn't wait 30 seconds.
        try:
            # Check for presence quickly
            await link.wait_for(state='attached', timeout=3000) 
            if not await link.is_visible():
                logger.info(f"Link for {page_type} ({link_texts}) found but not visible. Skipping.")
                return website_data
        except Exception:
            logger.info(f"Link for {page_type} ({link_texts}) not found on {page.url}. Skipping.")
            return website_data

        try:
            url = await link.get_attribute("href")
            if url:
                url = urljoin(page.url, url)
                if url and url != page.url:
                    logger.info(f"[{page_type}] Navigating from {page.url} to {url}")
                    if page_type == "About Us":
                        website_data.about_us_url = url
                    elif page_type == "Contact Us":
                        website_data.contact_url = url
                    elif page_type == "Services":
                        website_data.services_url = url
                    elif page_type == "Products":
                        website_data.products_url = url

                    await page.goto(url, wait_until="domcontentloaded", timeout=navigation_timeout_ms or 30000)
                    await scrape_function(page, website_data, browser)
        except Exception as e:
            logger.error(f"Error navigating to or scraping {page_type} page ({url if 'url' in locals() else 'unknown'}): {e}")
        return website_data

    async def _scrape_page(self, page: Page, website_data: Website, browser: BrowserContext) -> Website:
        html_content = await page.content()
        soup = BeautifulSoup(html_content, "html.parser")

        # 1. Detect technology
        detected_tech = self._detect_tech(soup)
        for t in detected_tech:
            if t not in website_data.tech_stack:
                website_data.tech_stack.append(t)

        # 2. Extract all emails
        email_map = self._extract_all_emails(soup, html_content)
        for email, label in email_map.items():
            if email not in website_data.all_emails:
                website_data.all_emails.append(email)
            if label and email not in website_data.email_contexts:
                website_data.email_contexts[email] = label

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
            if website_data.all_emails:
                # Prioritize emails that don't look like generic info/support if possible, 
                # but for now just pick the first one.
                website_data.email = website_data.all_emails[0]
                logger.info(f"SUCCESS: Found email from all_emails: {website_data.email}")
            else:
                text_content = soup.get_text(separator=' ')
                email_match = re.search(r"\b[a-zA-Z0-9._%+-]+ ?@ ?[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b", text_content)
                if email_match:
                    website_data.email = str(email_match.group(0)).replace(" ", "")
                    logger.info(f"SUCCESS: Found email: {website_data.email}")
                else:
                    logger.warning(f"No email found in text content of {page.url}")

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
            website_data.personnel.append({"email": match.replace(" ", "")})

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

    def _extract_all_emails(self, soup: BeautifulSoup, html_content: str = "") -> Dict[str, str]:
        """Returns a dict of email -> label/context found on the page."""
        email_to_label = {}
        
        # 1. From mailto: links (best source of names/labels)
        mailto_links = soup.find_all("a", href=re.compile(r"^mailto:", re.IGNORECASE))
        for link in mailto_links:
            href = link.get("href", "")
            if not isinstance(href, str):
                continue
            match = re.search(r"mailto:([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", href, re.IGNORECASE)
            if match:
                email = match.group(1).strip().lower()
                label = link.get_text(strip=True)
                # If label is just the email itself or too long, ignore it
                if label and email not in label.lower() and len(label) < 60:
                    email_to_label[email] = label
                elif email not in email_to_label:
                    email_to_label[email] = ""

        # 2. From text content (look for prefixes like "Contact: ", "Email: ")
        # We search for the email and then look at the 40 characters preceding it
        text_content = soup.get_text(separator=' ')
        # Find all emails in text
        text_emails = re.finditer(r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", text_content)
        for match in text_emails:
            email = match.group(1).strip().lower()
            if email not in email_to_label or not email_to_label[email]:
                # Look at prefix
                start = max(0, match.start() - 40)
                prefix = text_content[start:match.start()].strip()
                # Use regex to find common labels like "Contact: ", "Name - ", etc.
                label_match = re.search(r"([a-zA-Z]{3,20}(?:\s+[a-zA-Z]{3,20})?)\s*[:\-]\s*$", prefix)
                if label_match:
                    email_to_label[email] = label_match.group(1).strip()
                elif email not in email_to_label:
                    email_to_label[email] = ""

        # 3. From raw HTML (to catch emails in scripts, meta tags, etc.)
        if html_content:
            raw_emails = re.findall(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b", html_content)
            for email in raw_emails:
                email = email.strip().lower()
                if email not in email_to_label:
                    email_to_label[email] = ""
                
        return email_to_label

    def _detect_tech(self, soup: BeautifulSoup) -> List[str]:
        tech = set()
        
        # 1. Generator meta tag
        generator = soup.find("meta", attrs={"name": "generator"})
        if generator:
            content = generator.get("content")
            if content and isinstance(content, str):
                tech.add(content.strip())
            
        # 2. Common markers
        html_str = str(soup).lower()
        if "wp-content" in html_str:
            tech.add("WordPress")
        if "shopify" in html_str:
            tech.add("Shopify")
        if "wix.com" in html_str:
            tech.add("Wix")
        if "squarespace" in html_str:
            tech.add("Squarespace")
        if "wsimg.com" in html_str: # GoDaddy Website Builder usually uses wsimg.com for assets
            tech.add("GoDaddy Website Builder")
            
        return sorted(list(tech))
