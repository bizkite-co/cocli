import re
from cocli.core.prospects_csv_manager import ProspectsIndexManager
from cocli.core.config import get_campaign

campaign = get_campaign() or (lambda: exec('raise ValueError("No campaign")'))()
manager = ProspectsIndexManager(campaign)


# Robust area code extractor
def get_area_code(phone_str: str) -> str:
    if not phone_str:
        return ""
    match = re.search(r"^1?(\d{3})", str(phone_str))
    return match.group(1) if match else ""


problematic_prospects = []

print(f"Scanning all prospects for {campaign}...")
for prospect in manager.read_all_prospects():
    phone_str = str(prospect.phone or "")
    area_code = get_area_code(phone_str)

    if prospect.reviews_count is not None and str(prospect.reviews_count) == area_code:
        problematic_prospects.append(
            {
                "place_id": prospect.place_id,
                "reviews": prospect.reviews_count,
                "phone": phone_str,
            }
        )

print(f"Found {len(problematic_prospects)} problematic records in total index.")
for p in problematic_prospects:
    print(f"PlaceID: {p['place_id']}, Reviews: {p['reviews']}, Phone: {p['phone']}")
