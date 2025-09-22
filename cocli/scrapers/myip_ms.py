import csv
import re
from pathlib import Path
from typing import Optional, Dict, Any, List, Set, Tuple
from playwright.sync_api import sync_playwright, Page, Playwright
from bs4 import BeautifulSoup
import uuid
from datetime import datetime
import time
import random

from cocli.core.config import get_scraped_data_dir

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
    """Launches the browser and returns a new page with a specified viewport."""
    browser = p.chromium.launch(headless=False)
    page = browser.new_page(viewport={'width': 1280, 'height': 1950})
    return page

def _navigate_and_handle_captcha(page: Page, url: str, prompt_message: str, debug: bool) -> None:
    """Navigates to a URL, handles CAPTCHA if present, and introduces delays."""
    if debug: print(f"Debug: Navigating to {url}")
    page.goto(url, wait_until="domcontentloaded")
    _random_delay(4, 10)

    if _is_captcha_present(page):
        print(f"\n--- IMPORTANT: CAPTCHA detected on {page.url}. {prompt_message} ---")
        input("Press Enter after solving the CAPTCHA and the page has loaded...")
        print("Resuming...")
        _random_delay(4, 10)
    else:
        if debug: print(f"Debug: No CAPTCHA detected on {page.url}")

def _click_full_list_link(page: Page, debug: bool) -> None:
    """Finds and clicks the 'full list of sites' link."""
    full_list_link_selector = 'span:has(#sites_tbl_top) table:nth-of-type(2) a'
    try:
        full_list_link = page.locator(full_list_link_selector)
        if full_list_link.is_visible():
            print(f"Clicking link to full list of sites from {page.url}...")
            full_list_link.click()
            page.wait_for_load_state("domcontentloaded")
            _random_delay(8, 20)
            if debug: print(f"Debug: After clicking full list link. Current URL: {page.url}")
        else:
            print(f"Warning: Full list link not found or not visible on {page.url}.")
    except Exception as e:
        print(f"Error finding or clicking full list link on {page.url}: {e}.")

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
    print(f"Scraping content from actual URL: {current_url} (Segment: {actual_segment})...")

    soup = BeautifulSoup(page.content(), "html.parser")
    data_table = soup.select_one('#sites_tbl')

    if not data_table:
        print(f"Error: No data table found with ID '#sites_tbl' on segment {actual_segment}.")
        return 0

    rows = data_table.select("tr")
    if not rows:
        print(f"Error: No rows found within '#sites_tbl' on segment {actual_segment}.")
        return 0

    data_rows = [row for row in rows if row.select_one('td')]
    print(f"Found {len(data_rows)} potential data rows on segment {actual_segment}.")

    current_site_data = {}
    for row_index, row in enumerate(data_rows):
        if debug: print(f"Debug: Processing row {row_index}...")
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
            if debug: print(f"Debug: Main row data extracted: {current_site_data}")
        else:
            # This is an expand-child row, extract popularity
            popularity_div = row.select_one("div.stitle:-soup-contains('Website Popularity:') + div.sval")
            if popularity_div:
                popularity_text = popularity_div.get_text()
                match = re.search(r"([\d,]+)\s+visitors per day", popularity_text)
                if match:
                    current_site_data["Popularity_Visitors_Per_Day"] = match.group(1)

            if debug: print(f"Debug: Expand-child row popularity extracted: {current_site_data.get('Popularity_Visitors_Per_Day')}")

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
                    print(f"Scraped: {current_site_data['Website']} (Country: {current_site_data['Country']}, Popularity: {current_site_data['Popularity_Visitors_Per_Day']})")
                else:
                    if debug: print(f"Debug: Skipping {current_site_data['Website']} due to country: {current_site_data.get('Country')}")
            else:
                if debug: print(f"Debug: Skipping duplicate or invalid URL: {current_site_data.get('Website')}")

            current_site_data = {} # Clear for the next pair of rows

    return scraped_on_page_count

def scrape_myip_ms(
    ip_address: str,
    max_pages: int = 10,
    output_dir: Path = get_scraped_data_dir() / "shopify_csv",
    debug: bool = False,
) -> Optional[Path]:
    """
    Orchestrates scraping Shopify store information from myip.ms
    Requires user intervention for CAPTCHA.
    """
    if debug: print(f"Debug: scrape_myip_ms called with debug={debug}")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_filename = f"shopify-myip-ms-{ip_address.replace('.', '-')}-{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
    output_filepath = output_dir / output_filename

    with sync_playwright() as p:
        page = _initialize_browser(p)
        browser = page.context.browser # Keep browser reference for closing if needed

        try:
            _navigate_and_handle_captcha(
                page,
                f"https://myip.ms/info/whois/{ip_address}",
                "Please solve any CAPTCHA on the browser window.",
                debug
            )

            _click_full_list_link(page, debug)

            with open(output_filepath, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=SHOPIFY_HEADERS)
                writer.writeheader()

                processed_urls = set()
                total_scraped_count = 0

                for page_num in range(1, max_pages + 1):
                    if page_num > 1:
                        _navigate_and_handle_captcha(
                            page,
                            f"https://myip.ms/browse/sites/{page_num}/ipID/{ip_address}/ipIDii/{ip_address}",
                            f"CAPTCHA detected on page segment {page_num}. Please solve it.",
                            debug
                        )

                    scraped_on_page = _extract_data_from_page(page, ip_address, processed_urls, writer, debug)
                    total_scraped_count += scraped_on_page
                    print(f"Scraped {scraped_on_page} new records from page segment {_get_current_segment_from_url(page.url)}. Total scraped: {total_scraped_count}")

                    # Check if there are more pages to navigate to, or if we hit max_pages
                    # This logic might need refinement based on actual pagination elements
                    if page_num < max_pages:
                        print(f"Proceeding to next page after random delay...")
                        _random_delay(4, 10) # Delay before navigating to the next page
                    else:
                        print(f"Reached max_pages ({max_pages}). Stopping pagination.")


            print(f"Scraping complete. Total {total_scraped_count} Shopify stores scraped. Results saved to {output_filepath}")
            return output_filepath

        except Exception as e:
            print(f"An error occurred during myip.ms scraping: {e}")
            return None
        finally:
            # Do NOT close the browser during debugging
            # browser.close()
            print("\nBrowser left open for inspection. Please close it manually when done.")