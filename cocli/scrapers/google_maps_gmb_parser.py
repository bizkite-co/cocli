from bs4 import BeautifulSoup
from typing import Dict, Any

def parse_gmb_page(html: str, debug: bool = False) -> Dict[str, Any]:
    """
    Parses the HTML of a Google My Business page to extract additional information.
    """
    soup = BeautifulSoup(html, "html.parser")
    data = {}

    # Extract website
    website_element = soup.find("a", {"data-item-id": "authority"})
    if website_element and website_element.has_attr("href"):
        data["Website"] = website_element["href"]

    # Extract address
    address_element = soup.find("button", {"data-item-id": "address"})
    if address_element:
        data["Full_Address"] = address_element.get_text(strip=True).replace("", "")

    # Extract reviews
    reviews = []
    review_elements = soup.find_all("div", {"class": "review-snippet"})
    for review_element in review_elements:
        reviews.append(review_element.get_text(strip=True))
    data["Reviews"] = "\n".join(reviews)

    # Extract thumbnail URL
    thumbnail_element = soup.find("meta", {"property": "og:image"})
    if thumbnail_element and thumbnail_element.has_attr("content"):
        data["Thumbnail_URL"] = thumbnail_element["content"]

    return data
