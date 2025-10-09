import re
from pathlib import Path
from typing import Optional, List, Callable
from playwright.sync_api import sync_playwright, Page
from bs4 import BeautifulSoup
import logging
from urllib.parse import urljoin

from .base import EnrichmentScript
from ..models.company import Company
from ..models.website import Website

logger = logging.getLogger(__name__)

class WebsiteScraper(EnrichmentScript):
    def get_script_name(self) -> str:
        return "web-scraper"

    def run(
        self,
        company: Company,
        headed: bool = False,
        devtools: bool = False,
        debug: bool = False
    ) -> Website:
        if not company.domain:
            logger.info(f"Company {company.name} has no website URL. Skipping website scraping.")
            return Website(url=company.domain or "")

        logger.info(f"Starting website scraping for {company.name} at {company.domain}")

        website_data = Website(url=company.domain)

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=not headed, devtools=devtools)
                page = browser.new_page(viewport={'width': 1536, 'height': 1700})
                page.goto(f"http://{company.domain}", wait_until="domcontentloaded", timeout=30000)

                # Scrape main page
                website_data = self._scrape_page(page, website_data)

                # Scrape About Us and Contact Us pages
                website_data = self._navigate_and_scrape(page, website_data, ["About Us", "About"], "About Us", self._scrape_page, debug)
                website_data = self._navigate_and_scrape(page, website_data, ["Contact Us", "Contact"], "Contact Us", self._scrape_contact_page, debug)
                website_data = self._navigate_and_scrape(page, website_data, ["Services", "Products"], "Services", self._scrape_services_page, debug)

                browser.close()
        except Exception as e:
            logger.error(f"Error during website scraping for {company.name}: {e}")

        return website_data

    def _scrape_services_page(self, page: Page, website_data: Website) -> Website:
        html_content = page.content()
        soup = BeautifulSoup(html_content, "html.parser")

        # Look for list items or headings that might contain service names
        service_elements = soup.select('li, h2, h3')

        services = []
        for element in service_elements:
            text = element.get_text(strip=True)
            # Filter out short or irrelevant text
            if len(text) > 3 and len(text) < 100:
                services.append(text)

        website_data.services = list(set(services))
        logger.info(f"Found {len(website_data.services)} potential services on {page.url}")

        return website_data

    def _navigate_and_scrape(self, page: Page, website_data: Website, link_texts: List[str], page_type: str, scrape_function: Callable, debug: bool):
        link_selector = ", ".join([f'a:has-text("{text}")' for text in link_texts])
        link = page.locator(link_selector).first
        if link.is_visible():
            url = link.get_attribute("href")
            if url:
                url = urljoin(page.url, url)
                if url and url != page.url:
                    logger.info(f"Navigating to {page_type} page: {url}")
                    if page_type == "About Us":
                        website_data.about_us_url = url
                    elif page_type == "Contact Us":
                        website_data.contact_url = url
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=30000)
                        website_data = scrape_function(page, website_data)
                    except Exception as e:
                        logger.warning(
                            f"Failed to navigate or scrape {page_type} page for {website_data.url}: {e}"
                        )

        return website_data

    def _scrape_page(self, page: Page, website_data: Website) -> Website:
        html_content = page.content()
        soup = BeautifulSoup(html_content, "html.parser")

        # Extract Phone Number
        if not website_data.phone:
            phone_match = re.search(r"(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})", soup.get_text())
            if phone_match:
                website_data.phone = phone_match.group(0)
                logger.info(f"Found phone number: {website_data.phone}")

        # Extract Email
        if not website_data.email:
            email_match = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", soup.get_text())
            if email_match:
                website_data.email = email_match.group(0)
                logger.info(f"Found email: {website_data.email}")

        # Extract Social Media URLs
        if not website_data.facebook_url:
            facebook_link = soup.find("a", href=re.compile(r"facebook\.com", re.IGNORECASE))
            if facebook_link:
                website_data.facebook_url = facebook_link["href"]
                logger.info(f"Found Facebook URL: {website_data.facebook_url}")

        if not website_data.linkedin_url:
            linkedin_link = soup.find("a", href=re.compile(r"linkedin\.com", re.IGNORECASE))
            if linkedin_link:
                website_data.linkedin_url = linkedin_link["href"]
                logger.info(f"Found LinkedIn URL: {website_data.linkedin_url}")

        if not website_data.instagram_url:
            instagram_link = soup.find("a", href=re.compile(r"instagram\.com", re.IGNORECASE))
            if instagram_link:
                website_data.instagram_url = instagram_link["href"]
                logger.info(f"Found Instagram URL: {website_data.instagram_url}")

        if not website_data.twitter_url:
            twitter_link = soup.find("a", href=re.compile(r"twitter\.com", re.IGNORECASE))
            if twitter_link:
                website_data.twitter_url = twitter_link["href"]
                logger.info(f"Found Twitter URL: {website_data.twitter_url}")

        if not website_data.youtube_url:
            youtube_link = soup.find("a", href=re.compile(r"youtube\.com", re.IGNORECASE))
            if youtube_link:
                website_data.youtube_url = youtube_link["href"]
                logger.info(f"Found Youtube URL: {website_data.youtube_url}")

        # Extract Address
        if not website_data.address:
            # A simple regex for US addresses
            address_match = re.search(r"\d+\s+([a-zA-Z]+\s+)+[a-zA-Z]+,?\s+[A-Z]{2}\s+\d{5}", soup.get_text())
            if address_match:
                website_data.address = address_match.group(0)
                logger.info(f"Found address: {website_data.address}")

        # Extract Description
        if not website_data.description:
            about_section = soup.find(id=re.compile("about", re.IGNORECASE)) or soup.find(class_=re.compile("about", re.IGNORECASE))
            if "about" in page.url and soup.find(string=re.compile("^About (U|u)s")):
                about_section = soup.find(string=re.compile("^About (U|u)s")).parent

            if about_section:
                website_data.description = about_section.get_text(separator='\n', strip=True)
                logger.info(f"Found description for {website_data.url}")

        return website_data

    def _scrape_contact_page(self, page: Page, website_data: Website) -> Website:
        # First, run the generic scraper to get the easy stuff
        website_data = self._scrape_page(page, website_data)

        # Now, look for more specific contact info
        html_content = page.content()
        soup = BeautifulSoup(html_content, "html.parser")

        # Example: find email addresses with roles
        email_matches = re.findall(r"(\w+\s*:\s*[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", soup.get_text())
        for match in email_matches:
            website_data.personnel.append(match)

        return website_data
