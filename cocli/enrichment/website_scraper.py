import re
import httpx
import asyncio
import xml.etree.ElementTree as ET
from typing import Optional, List, Callable, Coroutine, Any, Dict, Union, Tuple
from playwright.async_api import Page, Browser, BrowserContext
from bs4 import BeautifulSoup
import logging
from urllib.parse import urljoin
from datetime import datetime, timedelta

from ..models.website import Website
from ..core.website_domain_csv_manager import (
    WebsiteDomainCsvManager,
    CURRENT_SCRAPER_VERSION,
)
from ..core.s3_domain_manager import S3DomainManager
from ..core.s3_company_manager import S3CompanyManager
from ..models.website_domain_csv import WebsiteDomainCsv
from ..models.campaign import Campaign
from ..core.exceptions import EnrichmentError
from ..core.email_index_manager import EmailIndexManager
from ..models.email import EmailEntry
from ..models.email_address import EmailAddress
from ..core.text_utils import is_valid_email
from ..utils.headers import ANTI_BOT_HEADERS, USER_AGENT


logger = logging.getLogger(__name__)


class WebsiteScraper:
    def __init__(self) -> None:
        self.headers = ANTI_BOT_HEADERS
        self.user_agent = USER_AGENT

    def _index_emails(self, website_data: Website, campaign_name: str) -> None:
        """Helper to record all found emails in the centralized email index."""
        if not website_data.url:
            return

        index_manager = EmailIndexManager(campaign_name)
        company_slug = website_data.associated_company_folder or "unknown"

        # 1. All found emails
        for email in website_data.all_emails:
            entry = EmailEntry(
                email=email,
                domain=str(website_data.url),
                company_slug=company_slug,
                source="website_scraper",
                tags=website_data.tags,
            )
            index_manager.add_email(entry)

        # 2. Personnel emails
        if website_data.personnel:
            for person in website_data.personnel:
                person_email = person.get("email")
                if person_email and isinstance(person_email, str):
                    try:
                        email_addr = EmailAddress(person_email)
                        entry = EmailEntry(
                            email=email_addr,
                            domain=str(website_data.url),
                            company_slug=company_slug,
                            source="website_scraper_personnel",
                            tags=website_data.tags,
                        )
                        if person.get("name"):
                            entry.tags.append(f"person:{person['name']}")
                        index_manager.add_email(entry)
                    except Exception:
                        continue

    async def _resolve_canonical_url(self, domain: str) -> Optional[str]:
        """Rapidly find the working URL for a domain, following redirects."""
        protocols = ["http://", "https://"]
        for protocol in protocols:
            url = f"{protocol}{domain}"
            try:
                async with httpx.AsyncClient(
                    follow_redirects=True, verify=False
                ) as client:
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
        company_slug: Optional[str] = None,
        force_refresh: bool = False,
        ttl_days: int = 30,
        debug: bool = False,
        campaign: Optional[Campaign] = None,
        navigation_timeout_ms: int = 30000,
        site_timeout_seconds: int = 120,
    ) -> Website:
        """
        Scrapes a website for company information.
        """
        website_data = Website(url=domain, scraper_version=CURRENT_SCRAPER_VERSION)
        if company_slug:
            website_data.associated_company_folder = company_slug

        try:
            await asyncio.wait_for(
                self._run_internal(
                    browser,
                    domain,
                    website_data,
                    force_refresh,
                    ttl_days,
                    debug,
                    campaign,
                    navigation_timeout_ms,
                ),
                timeout=site_timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.error(f"Scraping timed out for {domain} after {site_timeout_seconds} seconds. Finalizing with partial data.")
        finally:
            await self._finalize_enrichment(website_data, campaign)

        return website_data

    async def _finalize_enrichment(self, website_data: Website, campaign: Optional[Campaign] = None) -> None:
        """Saves and indexes the collected data."""
        if not website_data.url or website_data.url == "unknown":
            return

        domain_index_manager: Union[WebsiteDomainCsvManager, S3DomainManager]
        if campaign and campaign.aws and campaign.aws.profile:
            domain_index_manager = S3DomainManager(campaign=campaign)
        else:
            domain_index_manager = WebsiteDomainCsvManager()

        s3_company_manager: Optional[S3CompanyManager] = None
        if campaign:
            try:
                s3_company_manager = S3CompanyManager(campaign=campaign)
            except Exception as e:
                logger.warning(f"Could not initialize S3CompanyManager for finalization: {e}")

        # 1. Save to S3 if configured
        if (
            s3_company_manager
            and website_data.associated_company_folder
        ):
            try:
                await s3_company_manager.save_website_enrichment(
                    website_data.associated_company_folder, website_data
                )
            except Exception as e:
                logger.error(f"Failed to save website enrichment to S3 during finalization: {e}")

        # 2. Process keywords
        found_keywords = website_data.found_keywords
        if isinstance(found_keywords, str):
            try:
                import json
                found_keywords = json.loads(found_keywords.replace("'", '"'))
            except Exception:
                found_keywords = [found_keywords] if found_keywords else []
        website_data.found_keywords = found_keywords

        # 3. Add to domain index (local cache)
        valid_all_emails = [
            e for e in website_data.all_emails if is_valid_email(str(e))
        ]
        valid_email = (
            website_data.email
            if website_data.email and is_valid_email(str(website_data.email))
            else (valid_all_emails[0] if valid_all_emails else None)
        )

        try:
            domain_index_manager.add_or_update(
                WebsiteDomainCsv(
                    domain=str(website_data.url),
                    company_name=website_data.company_name,
                    phone=website_data.phone,
                    email=valid_email,
                    facebook_url=website_data.facebook_url,
                    linkedin_url=website_data.linkedin_url,
                    instagram_url=website_data.instagram_url,
                    twitter_url=website_data.twitter_url,
                    youtube_url=website_data.youtube_url,
                    address=website_data.address,
                    personnel=[str(p.get("name", "")) for p in website_data.personnel]
                    if website_data.personnel
                    else [],
                    about_us_url=website_data.about_us_url,
                    contact_url=website_data.contact_url,
                    services_url=website_data.services_url,
                    products_url=website_data.products_url,
                    tags=website_data.tags,
                    scraper_version=website_data.scraper_version,
                    associated_company_folder=website_data.associated_company_folder,
                    is_email_provider=website_data.is_email_provider,
                    all_emails=valid_all_emails,
                    email_contexts={
                        str(k): v
                        for k, v in website_data.email_contexts.items()
                        if is_valid_email(str(k))
                    },
                    tech_stack=website_data.tech_stack,
                    found_keywords=found_keywords,
                    updated_at=datetime.utcnow(),
                )
            )
        except Exception as e:
            logger.error(f"Failed to update domain index during finalization: {e}")

        # 4. Index emails for Outreach
        if campaign:
            try:
                self._index_emails(website_data, campaign.name)
            except Exception as e:
                logger.error(f"Failed to index emails during finalization: {e}")

    async def _run_internal(
        self,
        browser: Union[Browser, BrowserContext],
        domain: str,
        website_data: Website,
        force_refresh: bool = False,
        ttl_days: int = 30,
        debug: bool = False,
        campaign: Optional[Campaign] = None,
        navigation_timeout_ms: int = 30000,
    ) -> Website:
        """
        Internal implementation of website scraping.
        """
        domain_index_manager: Union[WebsiteDomainCsvManager, S3DomainManager]

        if campaign and campaign.aws and campaign.aws.profile:
            domain_index_manager = S3DomainManager(campaign=campaign)
        else:
            domain_index_manager = WebsiteDomainCsvManager()

        fresh_delta = timedelta(days=ttl_days)

        indexed_item = domain_index_manager.get_by_domain(domain)
        if indexed_item:
            is_stale = (datetime.utcnow() - indexed_item.updated_at) >= fresh_delta
            is_old_version = (
                indexed_item.scraper_version or 1
            ) < CURRENT_SCRAPER_VERSION
            if not force_refresh and not is_stale and not is_old_version:
                logger.info(f"Using indexed data for {domain}")
                data = indexed_item.model_dump()
                if "personnel" in data and isinstance(data["personnel"], list):
                    data["personnel"] = [
                        p for p in data["personnel"] if isinstance(p, dict)
                    ]
                return Website(**data)

        logger.info(f"Starting website scraping for {domain}")
        # website_data is already initialized by run()

        context: BrowserContext
        if isinstance(browser, Browser):
            context = await browser.new_context(
                ignore_https_errors=True,
                user_agent=self.user_agent,
                extra_http_headers=self.headers,
            )
        else:
            context = browser

        page = await context.new_page()
        try:
            canonical_url = await self._resolve_canonical_url(domain)
            if not canonical_url:
                canonical_url = f"https://{domain}"

            try:
                response = await page.goto(
                    canonical_url, wait_until="load", timeout=navigation_timeout_ms
                )
                if not response or not response.ok:
                    status = response.status if response else "No Response"
                    raise Exception(f"Navigation failed with status {status}")
                website_data.url = page.url
            except Exception as e:
                raise Exception(f"Could not navigate to {domain}. Error: {e}")

            target_keywords: List[str] = []
            if campaign:
                target_keywords = campaign.prospecting.queries + campaign.prospecting.keywords

            await self._scrape_page(page, website_data, context, target_keywords)

            if not (website_data.email and not target_keywords):
                sitemap_pages, sitemap_xml = await self._get_sitemap_urls(
                    f"http://{domain}"
                )
                website_data.sitemap_xml = sitemap_xml
                if sitemap_pages:
                    # 1. Identify high-priority URLs
                    page_map = {
                        "About Us": ["about"],
                        "Contact Us": ["contact"],
                        "Services": ["service"],
                        "Products": ["product"],
                    }
                    
                    urls_to_scrape: Dict[str, Tuple[str, Callable[..., Coroutine[Any, Any, Website]]]] = {} # url -> (type, func)
                    
                    # Search for standard pages
                    for page_type, keywords in page_map.items():
                        for keyword in keywords:
                            for url in sitemap_pages:
                                if url not in urls_to_scrape and keyword in url.lower():
                                    scrape_func: Callable[..., Coroutine[Any, Any, Website]] = self._scrape_page
                                    if page_type == "Contact Us":
                                        scrape_func = self._scrape_contact_page
                                    elif page_type == "Services":
                                        scrape_func = self._scrape_services_page
                                    elif page_type == "Products":
                                        scrape_func = self._scrape_products_page
                                    
                                    urls_to_scrape[url] = (page_type, scrape_func)
                                    break # Found one for this type

                    # Search for keyword-specific pages
                    if target_keywords:
                        for url in sitemap_pages:
                            if len(urls_to_scrape) >= 10:
                                break
                            if url not in urls_to_scrape and any(k.lower() in url.lower() for k in target_keywords):
                                urls_to_scrape[url] = ("Keyword Search", self._scrape_page)

                    # Fill remaining slots with generic pages if we haven't hit 10
                    if len(urls_to_scrape) < 10:
                        for url in sitemap_pages:
                            if len(urls_to_scrape) >= 10:
                                break
                            if url not in urls_to_scrape:
                                urls_to_scrape[url] = ("Generic", self._scrape_page)

                    # 2. Execute scraping with concurrency limit
                    semaphore = asyncio.Semaphore(3)

                    async def sem_scrape(url: str, p_type: str, s_func: Callable[..., Coroutine[Any, Any, Website]]) -> None:
                        async with semaphore:
                            page = None
                            try:
                                page = await context.new_page()
                                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                                await s_func(page, website_data, context, target_keywords)
                            except Exception:
                                pass
                            finally:
                                if page:
                                    await page.close()

                    scrape_tasks = [
                        sem_scrape(url, p_type, s_func) 
                        for url, (p_type, s_func) in urls_to_scrape.items()
                    ]
                    
                    if scrape_tasks:
                        await asyncio.gather(*scrape_tasks)

                if not website_data.about_us_url:
                    await self._navigate_and_scrape(
                        page,
                        website_data,
                        ["About", "About Us", "Our Story", "Company"],
                        "About Us",
                        self._scrape_page,
                        context,
                        debug,
                        navigation_timeout_ms,
                        target_keywords,
                    )
                if not website_data.contact_url:
                    await self._navigate_and_scrape(
                        page,
                        website_data,
                        [
                            "Contact",
                            "Contacts",
                            "Contact Us",
                            "Get in Touch",
                            "Reach Us",
                        ],
                        "Contact Us",
                        self._scrape_contact_page,
                        context,
                        debug,
                        navigation_timeout_ms,
                        target_keywords,
                    )
                if not website_data.services:
                    await self._navigate_and_scrape(
                        page,
                        website_data,
                        ["Services"],
                        "Services",
                        self._scrape_services_page,
                        context,
                        debug,
                        navigation_timeout_ms,
                        target_keywords,
                    )
                if not website_data.products:
                    await self._navigate_and_scrape(
                        page,
                        website_data,
                        ["Products"],
                        "Products",
                        self._scrape_products_page,
                        context,
                        debug,
                        navigation_timeout_ms,
                        target_keywords,
                    )

        except Exception as e:
            logger.error(f"Error scraping {domain}: {e}")
            raise EnrichmentError(str(e)) from e
        finally:
            await page.close()
            if isinstance(browser, Browser):
                await context.close()

        return website_data

    async def _scrape_sitemap_page(
        self,
        url: str,
        page_type: str,
        scrape_func: Callable[..., Coroutine[Any, Any, Website]],
        website_data: Website,
        browser: BrowserContext,
        debug: bool,
        target_keywords: List[str] = [],
    ) -> None:
        try:
            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await scrape_func(page, website_data, browser, target_keywords)
            await page.close()
        except Exception:
            pass

    async def _get_sitemap_urls(self, domain: str) -> Tuple[List[str], Optional[str]]:
        all_urls = set()
        raw_xml = None
        async with httpx.AsyncClient(follow_redirects=True) as client:
            for loc in ["/sitemap.xml", "/sitemap_index.xml", "/sitemap.desktop.xml"]:
                try:
                    resp = await client.get(urljoin(domain, loc), timeout=5)
                    if resp.status_code == 200:
                        if not raw_xml:
                            raw_xml = resp.text
                        root = ET.fromstring(resp.content)
                        if "sitemapindex" in root.tag:
                            for sm in root.iter():
                                if "loc" in sm.tag and sm.text:
                                    try:
                                        sub_resp = await client.get(sm.text, timeout=5)
                                        if sub_resp.status_code == 200:
                                            sub_root = ET.fromstring(sub_resp.content)
                                            for elem in sub_root.iter():
                                                if "loc" in elem.tag and elem.text:
                                                    all_urls.add(elem.text)
                                    except Exception:
                                        continue
                        else:
                            for elem in root.iter():
                                if "loc" in elem.tag and elem.text:
                                    all_urls.add(elem.text)
                except Exception:
                    continue
        return list(all_urls), raw_xml

    async def _scrape_services_page(
        self,
        page: Page,
        website_data: Website,
        browser: BrowserContext,
        target_keywords: List[str] = [],
    ) -> Website:
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")
        if target_keywords:
            self._search_keywords(soup, website_data, target_keywords)

        found_services = [
            el.get_text(strip=True)
            for el in soup.select("li, h2, h3")
            if 3 < len(el.get_text(strip=True)) < 100
        ]
        website_data.services = list(set(website_data.services + found_services))
        return website_data

    async def _scrape_products_page(
        self,
        page: Page,
        website_data: Website,
        browser: BrowserContext,
        target_keywords: List[str] = [],
    ) -> Website:
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")
        if target_keywords:
            self._search_keywords(soup, website_data, target_keywords)

        found_products = [
            el.get_text(strip=True)
            for el in soup.select("li, h2, h3")
            if 3 < len(el.get_text(strip=True)) < 100
        ]
        website_data.products = list(set(website_data.products + found_products))
        return website_data

    async def _navigate_and_scrape(
        self,
        page: Page,
        website_data: Website,
        link_texts: List[str],
        page_type: str,
        scrape_func: Callable[..., Coroutine[Any, Any, Website]],
        browser: BrowserContext,
        debug: bool,
        timeout: int,
        target_keywords: List[str] = [],
    ) -> Website:
        link = page.locator(
            ", ".join([f'a:text-matches("{t}", "i")' for t in link_texts])
        ).first
        try:
            await link.wait_for(state="attached", timeout=3000)
            url = await link.get_attribute("href")
            if url:
                if any(
                    url.lower().endswith(ext)
                    for ext in [".jpg", ".jpeg", ".png", ".gif", ".pdf", ".zip", ".mp4"]
                ):
                    return website_data

                url = urljoin(page.url, url)
                if url and url != page.url:
                    if page_type == "About Us":
                        website_data.about_us_url = url
                    elif page_type == "Contact Us":
                        website_data.contact_url = url
                    elif page_type == "Services":
                        website_data.services_url = url
                    elif page_type == "Products":
                        website_data.products_url = url

                    await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                    await scrape_func(page, website_data, browser, target_keywords)
        except Exception:
            pass
        return website_data

    async def _scrape_page(
        self,
        page: Page,
        website_data: Website,
        browser: BrowserContext,
        target_keywords: List[str] = [],
    ) -> Website:
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")
        if target_keywords:
            self._search_keywords(soup, website_data, target_keywords)

        # 1. Detect technology
        detected_tech = self._detect_tech(soup)
        for t in detected_tech:
            if t not in website_data.tech_stack:
                website_data.tech_stack.append(t)

        if not website_data.navbar_html:
            nav = soup.find("nav") or soup.select_one("[class*=nav], [id*=nav], header")
            if nav:
                website_data.navbar_html = str(nav)

        email_map = self._extract_all_emails(soup, html)
        for e_str, label in email_map.items():
            try:
                addr = EmailAddress(e_str)
                if addr not in website_data.all_emails:
                    website_data.all_emails.append(addr)
                if label:
                    website_data.email_contexts[addr] = label
            except Exception:
                continue

        if not website_data.email and website_data.all_emails:
            website_data.email = website_data.all_emails[0]

        # Extract Company Name
        if not website_data.company_name:
            company_name = None
            if soup.title and soup.title.string:
                company_name = soup.title.string.split("|")[0].split("-")[0].strip()
            if not company_name or len(company_name) < 3:
                h1 = soup.find("h1")
                if h1 and h1.string:
                    company_name = h1.string.strip()
            if not company_name or len(company_name) < 3:
                logo = soup.select_one("[class*=logo], [id*=logo]")
                if logo and logo.text:
                    company_name = logo.text.strip()
            if company_name and len(company_name) > 2:
                website_data.company_name = company_name

        if not website_data.phone:
            match = re.search(
                r"\b(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})\b", soup.get_text()
            )
            if match:
                try:
                    from cocli.models.phone import PhoneNumber

                    website_data.phone = PhoneNumber.model_validate(match.group(0))
                except Exception:
                    pass

        for platform in ["facebook", "linkedin", "instagram", "twitter", "youtube"]:
            if not getattr(website_data, f"{platform}_url"):
                link = soup.find("a", href=re.compile(f"{platform}\\.com", re.I))
                if link:
                    setattr(website_data, f"{platform}_url", str(link["href"]))

        # Extract Description
        if page.url == website_data.about_us_url:
            main_content = soup.select_one(
                "main, article, #main, #content, .main, .content"
            )
            if main_content:
                for tag in main_content.select("nav, footer"):
                    tag.decompose()
                website_data.description = str(
                    main_content.get_text(separator="\n", strip=True)
                )
            else:
                if soup.body:
                    for tag in soup.body.select("nav, footer, header"):
                        tag.decompose()
                    website_data.description = str(
                        soup.body.get_text(separator="\n", strip=True)
                    )
        elif not website_data.description:
            about_section = soup.find(
                id=re.compile("about", re.IGNORECASE)
            ) or soup.find(class_=re.compile("about", re.IGNORECASE))
            if about_section:
                website_data.description = str(
                    about_section.get_text(separator="\n", strip=True)
                )

        return website_data

    async def _scrape_contact_page(
        self,
        page: Page,
        website_data: Website,
        browser: BrowserContext,
        target_keywords: List[str] = [],
    ) -> Website:
        await self._scrape_page(page, website_data, browser, target_keywords)
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")
        for match in re.findall(
            r"(\w+\s*:\s*[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})",
            soup.get_text(),
        ):
            website_data.personnel.append({"email": match.replace(" ", "")})

        # Look for personnel links
        personnel_selectors = [
            ".member__wrapper",
            ".person__card",
            ".team__member",
            ".staff__item",
        ]
        personnel_elements = soup.select(", ".join(personnel_selectors))
        for element in personnel_elements:
            link = element.find("a", href=True)
            if link and link["href"]:
                person_url = urljoin(str(page.url), str(link["href"]))
                if person_url and person_url != page.url:
                    person_page = await browser.new_page()
                    try:
                        await person_page.goto(
                            person_url, wait_until="domcontentloaded", timeout=30000
                        )
                        person_data = await self._scrape_personnel_details(
                            person_page, website_data
                        )
                        if person_data:
                            website_data.personnel.append(person_data)
                    except Exception:
                        pass
                    finally:
                        await person_page.close()
        return website_data

    async def _scrape_personnel_details(
        self, page: Page, website_data: Website
    ) -> Optional[Dict[str, Any]]:
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")
        person_data: Dict[str, Any] = {}
        name_element = soup.select_one("h1, .member__name, .person__name")
        if name_element:
            person_data["name"] = name_element.get_text(strip=True)
        title_element = soup.select_one(
            ".member__position, .person__position, .person__title"
        )
        if title_element:
            person_data["title"] = title_element.get_text(strip=True)
        email_match = re.search(
            r"\b[a-zA-Z0-9._%+-]+ ?@ ?[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b", soup.get_text()
        )
        if email_match:
            try:
                person_data["email"] = EmailAddress(
                    email_match.group(0).replace(" ", "")
                )
            except Exception:
                pass
        linkedin_link = soup.find("a", href=re.compile(r"linkedin\.com/in/", re.I))
        if linkedin_link:
            person_data["linkedin_url"] = str(linkedin_link["href"])
        phone_match = re.search(
            r"\b(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})\b", soup.get_text()
        )
        if phone_match:
            person_data["phone"] = str(phone_match.group(0))
        return person_data if person_data else None

    def _search_keywords(
        self, soup: BeautifulSoup, website_data: Website, target_keywords: List[str]
    ) -> None:
        text = soup.get_text(separator=" ", strip=True).lower()
        for k in target_keywords:
            if k.lower() in text and k not in website_data.found_keywords:
                website_data.found_keywords.append(k)
                logger.info(f"Found keyword '{k}' on {website_data.url}")

    def _extract_all_emails(
        self, soup: BeautifulSoup, html: str = ""
    ) -> Dict[str, str]:
        email_to_label = {}
        for link in soup.find_all("a", href=re.compile(r"^mailto:", re.I)):
            href_attr = link.get("href")
            if not href_attr or not isinstance(href_attr, str):
                continue
            m = re.search(
                r"mailto:([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})",
                href_attr,
                re.I,
            )
            if m:
                email = m.group(1).lower()
                label = link.get_text(strip=True)
                if label and email not in label.lower() and len(label) < 60:
                    email_to_label[email] = label
                elif email not in email_to_label:
                    email_to_label[email] = ""

        text_content = soup.get_text(separator=" ")
        for match in re.finditer(
            r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", text_content
        ):
            email = match.group(1).lower()
            if email not in email_to_label or not email_to_label[email]:
                prefix = text_content[
                    max(0, match.start() - 40) : match.start()
                ].strip()
                label_match = re.search(
                    r"([a-zA-Z]{3,20}(?:\s+[a-zA-Z]{3,20})?)\s*[:\-]\s*$", prefix
                )
                if label_match:
                    email_to_label[email] = label_match.group(1).strip()
                elif email not in email_to_label:
                    email_to_label[email] = ""

        if html:
            for email in re.findall(
                r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b", html
            ):
                email = email.lower()
                if email not in email_to_label:
                    email_to_label[email] = ""
        return email_to_label

    def _detect_tech(self, soup: BeautifulSoup) -> List[str]:
        tech = set()
        generator = soup.find("meta", attrs={"name": "generator"})
        if generator and (content := generator.get("content")):
            tech.add(str(content).strip())
        html_str = str(soup).lower()
        if "wp-content" in html_str:
            tech.add("WordPress")
        if "shopify" in html_str:
            tech.add("Shopify")
        if "wix.com" in html_str:
            tech.add("Wix")
        if "squarespace" in html_str:
            tech.add("Squarespace")
        if "wsimg.com" in html_str:
            tech.add("GoDaddy Website Builder")
        return sorted(list(tech))
