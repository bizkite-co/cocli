import re
from pathlib import Path
from typing import Optional, List
from playwright.sync_api import sync_playwright, Page
from bs4 import BeautifulSoup
import logging

from .base import EnrichmentScript
from ..core.models import Company

logger = logging.getLogger(__name__)

class WebsiteScraper(EnrichmentScript):
    def get_script_name(self) -> str:
        return "web-scraper"

    def run(self, company: Company) -> Company:
        if not company.website_url:
            logger.info(f"Company {company.name} has no website URL. Skipping website scraping.")
            return company

        logger.info(f"Starting website scraping for {company.name} at {company.website_url}")

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(company.website_url, wait_until="domcontentloaded", timeout=30000)

                # Scrape main page
                company = self._scrape_page(page, company)

                # Look for "About Us" page
                about_us_link = page.locator('a:has-text("About Us"), a:has-text("About")').first
                if about_us_link.is_visible():
                    about_us_url = about_us_link.get_attribute("href")
                    if about_us_url:
                        # Ensure the URL is absolute
                        if not about_us_url.startswith("http"):
                            base_url_match = re.match(r"(https?://[^/]+)", company.website_url)
                            if base_url_match:
                                base_url = base_url_match.group(0)
                                about_us_url = f"{base_url}{about_us_url}"
                            else:
                                logger.warning(f"Could not determine base URL for {company.website_url}")
                                about_us_url = None # Invalidate if base URL cannot be determined

                        if about_us_url and about_us_url != page.url: # Avoid re-scraping the same page
                            logger.info(f"Navigating to About Us page: {about_us_url}")
                            try:
                                page.goto(about_us_url, wait_until="domcontentloaded", timeout=30000)
                                company = self._scrape_page(page, company)
                            except Exception as e:
                                logger.warning(f"Failed to navigate or scrape About Us page for {company.name}: {e}")

                browser.close()
        except Exception as e:
            logger.error(f"Error during website scraping for {company.name}: {e}")

        return company

    def _scrape_page(self, page: Page, company: Company) -> Company:
        html_content = page.content()
        soup = BeautifulSoup(html_content, "html.parser")

        # Extract Phone Number
        if not company.phone_from_website:
            phone_match = re.search(r"(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})", soup.get_text())
            if phone_match:
                company.phone_from_website = phone_match.group(0)
                logger.info(f"Found phone number: {company.phone_from_website}")

        # Extract Email
        if not company.email:
            email_match = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", soup.get_text())
            if email_match:
                company.email = email_match.group(0)
                logger.info(f"Found email: {company.email}")

        # Extract Social Media URLs
        if not company.facebook_url:
            facebook_link = soup.find("a", href=re.compile(r"facebook\.com", re.IGNORECASE))
            if facebook_link:
                company.facebook_url = facebook_link["href"]
                logger.info(f"Found Facebook URL: {company.facebook_url}")

        if not company.linkedin_url:
            linkedin_link = soup.find("a", href=re.compile(r"linkedin\.com", re.IGNORECASE))
            if linkedin_link:
                company.linkedin_url = linkedin_link["href"]
                logger.info(f"Found LinkedIn URL: {company.linkedin_url}")

        if not company.instagram_url:
            instagram_link = soup.find("a", href=re.compile(r"instagram\.com", re.IGNORECASE))
            if instagram_link:
                company.instagram_url = instagram_link["href"]
                logger.info(f"Found Instagram URL: {company.instagram_url}")

        return company