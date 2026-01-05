from pathlib import Path
from bs4 import BeautifulSoup
from cocli.enrichment.website_scraper import WebsiteScraper

def test_extract_email_from_ace_installations_html():
    # Load the saved HTML
    html_path = Path("tests/data/websites/ace-installations.com.html")
    html_content = html_path.read_text()
    
    # Initialize scraper
    scraper = WebsiteScraper()
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Test the extraction logic
    email_map = scraper._extract_all_emails(soup, html_content)
    
    assert "gisele@ace-installations.com" in email_map

def test_extract_instagram_from_ace_installations_html():
    html_path = Path("tests/data/websites/ace-installations.com.html")
    html_content = html_path.read_text()
    
    soup = BeautifulSoup(html_content, "html.parser")
    
    import re
    instagram_link = soup.find("a", href=re.compile(r"instagram\.com", re.IGNORECASE))
    found_insta = str(instagram_link["href"]) if instagram_link else None
    
    assert found_insta == "https://www.instagram.com/ace_installationsny/"