import csv
import re
from pathlib import Path
from typing import Optional, Set
from playwright.sync_api import sync_playwright, Page, Playwright
from bs4 import BeautifulSoup
import uuid
from datetime import datetime
import time
import random
import logging

from cocli.core.config import get_scraped_data_dir

logger = logging.getLogger(__name__)

class LimitExceededError(Exception):
    pass

SHOPIFY_HEADERS = [
    "id",
    "Website",
    "IP_Address",
    "Popularity_Visitors_Per_Day",
    "Country",
    "Uuid",
    "Scrape_Date",
]

def _random_delay(min_sec: int, max_sec: int) -> None:
    """Introduces a random delay between min_sec and max_sec seconds."""
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)

def _is_captcha_present(page: Page) -> bool:
    """Checks if a CAPTCHA or human verification challenge is present on the page."""
    content = page.content()
    return "Human Verification" in content or page.locator('input#captcha_submit').is_visible()

def _get_current_segment_from_url(url: str) -> str:
    """Extracts the page segment number from a myip.ms /browse/sites/ URL."""
    match = re.search(r"/sites/(\d+)/", url)
    return match.group(1) if match else "Unknown"

def _initialize_browser(p: Playwright) -> Page:
    """Launches the browser and returns a new page in an incognito context."""
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(viewport={'width': 1280, 'height': 1950})
    page = context.new_page()
    return page

def _navigate_and_handle_captcha(page: Page, url: str, prompt_message: str, debug: bool) -> None:
    """
    Navigates to a URL, handles CAPTCHA if present, and introduces delays.
    """
    if debug: logger.debug(f"Debug: Navigating to {url}")
    page.goto(url, wait_until="domcontentloaded")

    if "myip.ms/info/limitexcess" in page.url:
        raise LimitExceededError("Page visit limit exceeded.")

    _random_delay(4, 10)

    if _is_captcha_present(page):
        logger.warning(f"\n--- IMPORTANT: CAPTCHA detected on {page.url}. {prompt_message} ---")
        input("Press Enter after solving the CAPTCHA and the page has loaded...")
        logger.info("Resuming...")
        page.wait_for_load_state('domcontentloaded')
        _random_delay(4, 10)
    else:
        if debug: logger.debug(f"Debug: No CAPTCHA detected on {page.url}")

def _click_full_list_link(page: Page, debug: bool) -> None:
    """Finds and clicks the 'full list of sites' link."""
    full_list_link_selector = 'span:has(#sites_tbl_top) table:nth-of-type(2) a'
    try:
        full_list_link = page.locator(full_list_link_selector)
        if full_list_link.is_visible():
            logger.info(f"Clicking link to full list of sites from {page.url}...")
            full_list_link.click()
            page.wait_for_load_state("domcontentloaded")
            _random_delay(8, 20)
            if debug: logger.debug(f"Debug: After clicking full list link. Current URL: {page.url}")
        else:
            logger.warning(f"Warning: Full list link not found or not visible on {page.url}.")
    except Exception as e:
        logger.error(f"Error finding or clicking full list link on {page.url}: {e}.")

def _extract_data_from_page(
    page: Page,
    ip_address: str,
    processed_urls: Set[str],
    writer: csv.DictWriter,
    debug: bool,
) -> int:
    """
    Extracts business data from the current page's HTML and writes to CSV.
    Returns the number of new records scraped on this page.
    """
    scraped_on_page_count = 0
    current_url = page.url
    actual_segment = _get_current_segment_from_url(current_url)
    logger.info(f"Scraping content from actual URL: {current_url} (Segment: {actual_segment})...")

    soup = BeautifulSoup(page.content(), "html.parser")
    data_table = soup.select_one('#sites_tbl')

    if not data_table:
        logger.error(f"Error: No data table found with ID '#sites_tbl' on segment {actual_segment}.")
        return 0

    rows = data_table.select("tr")
    if not rows:
        logger.error(f"Error: No rows found within '#sites_tbl' on segment {actual_segment}.")
        return 0

    data_rows = [row for row in rows if row.select_one('td')]
    logger.info(f"Found {len(data_rows)} potential data rows on segment {actual_segment}.")

    current_site_data = {}
    for row_index, row in enumerate(data_rows):
        if debug: logger.debug(f"Debug: Processing row {row_index}...")
        if "expand-child" not in row.attrs.get("class", []):
            # This is a main site listing row
            cols = row.select("td")
            if len(cols) > 1:
                website_url_element = cols[1].select_one("a")
                current_site_data["Website"] = website_url_element["href"] if website_url_element else ""

                ip_element = cols[2].select_one("a")
                current_site_data["IP_Address"] = ip_element.get_text(strip=True) if ip_element else ""

                country_element = cols[4]
                current_site_data["Country"] = country_element.getText()

                current_site_data["Popularity_Visitors_Per_Day"] = "" # Reset for new main row
            if debug: logger.debug(f"Debug: Main row data extracted: {current_site_data}")
        else:
            # This is an expand-child row, extract popularity
            popularity_div = row.select_one("div.stitle:-soup-contains('Website Popularity:') + div.sval")
            if popularity_div:
                popularity_text = popularity_div.get_text()
                match = re.search(r"([\d,]+)\s+visitors per day", popularity_text)
                if match:
                    current_site_data["Popularity_Visitors_Per_Day"] = match.group(1)

            if debug: logger.debug(f"Debug: Expand-child row popularity extracted: {current_site_data.get('Popularity_Visitors_Per_Day')}")

            if current_site_data.get("Website") and current_site_data["Website"] not in processed_urls:
                if current_site_data.get("Country") in ["United States", "Canada"]:
                    data = {
                        "id": str(uuid.uuid4()),
                        "Website": current_site_data["Website"],
                        "IP_Address": current_site_data["IP_Address"],
                        "Popularity_Visitors_Per_Day": current_site_data["Popularity_Visitors_Per_Day"],
                        "Country": current_site_data["Country"],
                        "Uuid": str(uuid.uuid4()),
                        "Scrape_Date": datetime.now().isoformat(),
                    }
                    writer.writerow(data)
                    processed_urls.add(current_site_data["Website"])
                    scraped_on_page_count += 1
                    logger.info(f"Scraped: {current_site_data['Website']} (Country: {current_site_data['Country']}, Popularity: {current_site_data['Popularity_Visitors_Per_Day']})")
                else:
                    if debug: logger.debug(f"Debug: Skipping {current_site_data['Website']} due to country: {current_site_data.get('Country')}")
            else:
                if debug: logger.debug(f"Debug: Skipping duplicate or invalid URL: {current_site_data.get('Website')}")

            current_site_data = {} # Clear for the next pair of rows

    return scraped_on_page_count

def scrape_myip_ms(
    ip_address: str,
    start_page: int = 1,
    end_page: int = 10,
    output_dir: Path = get_scraped_data_dir() / "shopify_csv",
    debug: bool = False,
) -> Optional[Path]:
    """
    Orchestrates scraping Shopify store information from myip.ms
    Requires user intervention for CAPTCHA.
    """
    if debug: logger.debug(f"Debug: scrape_myip_ms called with debug={debug}")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_filename = f"shopify-myip-ms-{ip_address.replace('.', '-')}-{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
    output_filepath = output_dir / output_filename

    with sync_playwright() as p:
        page = _initialize_browser(p)
        browser = page.context.browser # Keep browser reference for closing if needed

        try:
            # The file is now opened in append mode inside the loop.
            output_filepath.parent.mkdir(parents=True, exist_ok=True)

            if start_page == 1:
                _navigate_and_handle_captcha(
                    page,
                    f"https://myip.ms/info/whois/{ip_address}",
                    "Please solve any CAPTCHA on the browser window.",
                    debug
                )
                _click_full_list_link(page, debug)
            else:
                _navigate_and_handle_captcha(
                    page,
                    f"https://myip.ms/browse/sites/{start_page}/ipID/{ip_address}/ipIDii/{ip_address}",
                    f"CAPTCHA detected on page segment {start_page}. Please solve it.",
                    debug
                )

            processed_urls: set[str] = set() # This might need to be persisted across runs if we are appending.
            total_scraped_count = 0

            for page_num in range(start_page, end_page + 1):
                if page_num > start_page:
                    _navigate_and_handle_captcha(
                        page,
                        f"https://myip.ms/browse/sites/{page_num}/ipID/{ip_address}/ipIDii/{ip_address}",
                        f"CAPTCHA detected on page segment {page_num}. Please solve it.",
                        debug
                    )

                with open(output_filepath, "a", newline="", encoding="utf-8") as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=SHOPIFY_HEADERS)
                    if csvfile.tell() == 0:
                        writer.writeheader()

                    scraped_on_page = _extract_data_from_page(page, ip_address, processed_urls, writer, debug)
                    total_scraped_count += scraped_on_page
                
                logger.info(f"Scraped {scraped_on_page} new records from page segment {_get_current_segment_from_url(page.url)}. Total scraped: {total_scraped_count}")

                if page_num < end_page:
                    logger.info("Proceeding to next page after random delay...")
                    _random_delay(4, 10)
                else:
                    logger.info(f"Reached end_page ({end_page}). Stopping pagination.")

            logger.info(f"Scraping complete. Total {total_scraped_count} Shopify stores scraped. Results saved to {output_filepath}")
            return output_filepath

        except LimitExceededError as e:
            logger.warning(f"[bold yellow]Scraping paused:[/bold yellow] {e}")
            return output_filepath # Return the path to the partially saved file
        except Exception as e:
            logger.error(f"An error occurred during myip.ms scraping: {e}")
            return None
        finally:
            # Do NOT close the browser during debugging
            # browser.close()
            logger.info("\nBrowser left open for inspection. Please close it manually when done.")