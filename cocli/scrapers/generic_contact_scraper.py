import asyncio
import re
from typing import List, Dict, Any, Optional
import logging

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

class GenericContactScraper:
    def __init__(self):
        pass

    async def find_contact_pages(self, domain: str) -> List[str]:
        """
        Attempts to find potential contact pages for a given domain.
        """
        potential_paths = ["/contact", "/contact-us", "/about/contact", "/reach-us", "/get-in-touch"]
        base_url = f"http://{domain}"
        contact_urls = []

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()

            # Check common paths directly
            for path in potential_paths:
                full_url = f"{base_url}{path}"
                try:
                    response = await page.goto(full_url, wait_until="domcontentloaded", timeout=5000)
                    if response and response.status == 200:
                        logger.info(f"Found potential contact page: {full_url}")
                        contact_urls.append(full_url)
                except Exception:
                    pass # Page not found or other error

            # Also check links on the homepage
            try:
                await page.goto(base_url, wait_until="domcontentloaded")
                html_content = await page.content()
                soup = BeautifulSoup(html_content, 'html.parser')

                for a_tag in soup.find_all('a', href=True):
                    href = a_tag['href']
                    if "contact" in href.lower() or "about" in href.lower():
                        # Construct absolute URL if it's relative
                        if href.startswith('/'):
                            full_url = f"{base_url}{href}"
                        elif href.startswith(base_url):
                            full_url = href
                        else:
                            continue # Skip external links for now

                        if full_url not in contact_urls:
                            logger.info(f"Found potential contact link on homepage: {full_url}")
                            contact_urls.append(full_url)
            except Exception as e:
                logger.error(f"Error checking homepage for contact links: {e}")

            await browser.close()
        return list(set(contact_urls)) # Return unique URLs

    async def scrape_page_for_contacts(self, url: str) -> List[Dict[str, str]]:
        """
        Scrapes a given URL for email addresses, names, and roles.
        It looks for mailto: links and attempts to infer associated names and roles.
        """
        contacts = []
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded")
                html_content = await page.content()
                await browser.close()

            soup = BeautifulSoup(html_content, 'html.parser')

            # Find all mailto links within h5 tags
            for h5_tag in soup.find_all('h5'): # Iterate through h5 tags first
                a_tag = h5_tag.find('a', href=re.compile(r'^(mailto:|email:)'))
                if a_tag:
                    email = a_tag['href'].replace('mailto:', '').replace('email:', '').strip()
                    
                    # Skip if email is empty
                    if not email:
                        continue

                    name = a_tag.get_text(strip=True)
                    role = ""

                    # Attempt to infer role from text immediately following the <a> tag
                    next_sibling = a_tag.next_sibling
                    if next_sibling and isinstance(next_sibling, str):
                        role = next_sibling.strip()
                    
                    # If role is still empty, try a more general approach within the h5 tag
                    if not role:
                        full_text_in_h5 = h5_tag.get_text(separator=' ', strip=True)
                        # Remove the name and email from the full text to isolate the role
                        temp_text = full_text_in_h5.replace(name, '', 1).replace(email, '', 1).strip()
                        # Heuristic: if the remaining text is short and looks like a role
                        if len(temp_text) > 0 and len(temp_text) < 100 and not re.search(r'\d', temp_text):
                            role = temp_text.replace('&nbsp;', ' ').strip()
                            if role.startswith('-'):
                                role = role[1:].strip()

                    contacts.append({'name': name, 'email': email, 'role': role})
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
        return contacts

# Example usage (for testing)
async def main():
    scraper = GenericContactScraper()
    domain = "dsb-plus.com"
    contact_pages = await scraper.find_contact_pages(domain)
    logger.info(f"Discovered contact pages for {domain}: {contact_pages}")

    all_contacts = []
    for page_url in contact_pages:
        contacts = await scraper.scrape_page_for_contacts(page_url)
        all_contacts.extend(contacts)
    
    logger.info(f"All contacts found: {all_contacts}")

if __name__ == "__main__":
    asyncio.run(main())