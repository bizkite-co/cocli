import pytest
from pathlib import Path
from bs4 import BeautifulSoup
from cocli.enrichment.website_scraper import WebsiteScraper
from cocli.models.website import Website

def test_extract_email_from_ace_installations_html():
    # Load the saved HTML
    html_path = Path("tests/data/websites/ace-installations.com.html")
    html_content = html_path.read_text()
    
    # Initialize scraper and dummy data
    scraper = WebsiteScraper()
    website_data = Website(url="https://aceflooringgroup.com/")
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Simulate the email extraction part of _scrape_page
    # We manually replicate the logic here to see if it works on this HTML
    import re
    email_match = re.search(r"\b[a-zA-Z0-9._%+-]+ ?@ ?[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b", soup.get_text(separator=' '))
    
    found_email = None
    if email_match:
        found_email = str(email_match.group(0)).replace(" ", "")
        
    assert found_email == "Gisele@ace-installations.com"

def test_extract_instagram_from_ace_installations_html():
    html_path = Path("tests/data/websites/ace-installations.com.html")
    html_content = html_path.read_text()
    
    scraper = WebsiteScraper()
    soup = BeautifulSoup(html_content, "html.parser")
    
    import re
    instagram_link = soup.find("a", href=re.compile(r"instagram\.com", re.IGNORECASE))
    found_insta = str(instagram_link["href"]) if instagram_link else None
    
    assert found_insta == "https://www.instagram.com/ace_installationsny/"
