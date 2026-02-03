from bs4 import BeautifulSoup
from typing import Dict, Any

def parse_gmb_page(html: str, debug: bool = False) -> Dict[str, Any]:
    """
    Parses the HTML of a Google My Business page to extract additional information.
    """
    soup = BeautifulSoup(html, "html.parser")
    data = {}

    # --- EXTRACT NAME (High Priority) ---
    name = None
    
    # 1. Look for h1 (Standard for detailed view)
    h1_tag = soup.find("h1")
    if h1_tag:
        name = h1_tag.get_text(strip=True)
        
    # 2. Fallback: og:title meta tag (Usually 'Name · Location')
    if not name:
        name_meta = soup.find("meta", {"property": "og:title"})
        if name_meta and name_meta.has_attr("content"):
            content_val = str(name_meta["content"])
            # Google often formats as "Business Name · Location"
            name = content_val.split(" · ")[0]

    # 3. Fallback: ARIA labels on common elements
    if not name:
        label_tag = soup.find(attrs={"aria-label": True, "role": "main"})
        if label_tag:
            name = label_tag.get("aria-label")

    # 3. Fallback: ARIA label on role="main" or role="article"
    if not name:
        main_tag = soup.find(attrs={"role": "main", "aria-label": True}) or \
                   soup.find(attrs={"role": "article", "aria-label": True})
        if main_tag:
            name = main_tag.get("aria-label")

    if name:
        data["Name"] = name

    # --- EXTRACT WEBSITE ---
    # Look for the 'authority' data-item-id which is standard for website links
    website_element = soup.find("a", {"data-item-id": "authority"})
    if not website_element:
        # Fallback: Find any link with 'website' in the aria-label
        website_element = soup.find("a", attrs={"aria-label": lambda x: x and 'website' in x.lower()})
        
    if website_element and website_element.has_attr("href"):
        data["Website"] = str(website_element["href"])

    # --- EXTRACT PHONE ---
    phone_element = soup.find("button", {"data-item-id": lambda x: x and "phone" in x})
    if not phone_element:
        # Fallback: Look for tel: links
        phone_link = soup.find("a", href=lambda x: x and x.startswith("tel:"))
        if phone_link:
            data["Phone"] = phone_link.get("href", "").replace("tel:", "").strip()
    elif phone_element:
        data["Phone"] = phone_element.get_text(strip=True).replace("", "").strip()

    # --- EXTRACT ADDRESS ---
    address_element = soup.find("button", {"data-item-id": "address"})
    if address_element:
        data["Full_Address"] = address_element.get_text(strip=True).replace("", "")

    # --- EXTRACT REVIEWS ---
    reviews = []
    # This class is often randomized, but review text often appears in specific spans
    review_elements = soup.find_all("div", {"class": "review-snippet"})
    for review_element in review_elements:
        reviews.append(review_element.get_text(strip=True))
    if reviews:
        data["Reviews"] = "\n".join(reviews)

    # --- EXTRACT THUMBNAIL ---
    thumbnail_element = soup.find("meta", {"property": "og:image"})
    if thumbnail_element and thumbnail_element.has_attr("content"):
        data["Thumbnail_URL"] = str(thumbnail_element["content"])

    return data
