# POLICY: frictionless-data-policy-enforcement
import json
import logging
from bs4 import BeautifulSoup
from cocli.scrapers.google_maps_parsers.extract_rating_reviews_gm_details import extract_rating_reviews_gm_details
from cocli.core.paths import paths

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("test_parser")

def test_witnesses(campaign_name: str) -> None:
    completed_dir = paths.campaign(campaign_name).path / "raw" / "completed"
    batch_file = paths.campaign(campaign_name).path / "recovery" / "recovery_batch_200.txt"
    
    if not batch_file.exists():
        logger.error(f"Batch file not found: {batch_file}")
        return

    target_ids = []
    with open(batch_file, "r") as f:
        for line in f:
            if line.strip():
                target_ids.append(line.strip().split("|")[0])

    logger.info(f"Testing parser against {len(target_ids)} potential witnesses...")
    
    stats = {"found_file": 0, "has_rating": 0, "has_reviews": 0, "both": 0}
    
    for pid in target_ids:
        # Check both Legacy and New structure
        # Legacy: completed/{shard}/{pid}.json
        # New: completed/{shard}/{pid}/metadata.json + witness.html
        
        html = None
        
        # 1. Try Legacy
        legacy_path = list(completed_dir.rglob(f"{pid}.json"))
        if legacy_path and legacy_path[0].is_file() and legacy_path[0].name != "metadata.json":
            stats["found_file"] += 1
            with open(legacy_path[0], "r", encoding="utf-8") as f:
                data = json.load(f)
                html = data.get("html", "")
        
        # 2. Try New
        if not html:
            meta_path = list(completed_dir.rglob(f"{pid}/metadata.json"))
            if meta_path:
                stats["found_file"] += 1
                witness_dir = meta_path[0].parent
                html_path = witness_dir / "witness.html"
                if html_path.exists():
                    with open(html_path, "r", encoding="utf-8") as f:
                        html = f.read()

        if not html:
            continue
            
        soup = BeautifulSoup(html, "html.parser")
        inner_text = soup.get_text(separator="\n", strip=True)
        
        res = extract_rating_reviews_gm_details(soup, inner_text, debug=False)
        rating = res.get("Average_rating")
        reviews = res.get("Reviews_count")
        
        if rating:
            stats["has_rating"] += 1
        if reviews:
            stats["has_reviews"] += 1
        
        if rating and reviews: 
            stats["both"] += 1
            logger.info(f"  [OK] {pid}: {rating} ({reviews} reviews)")
        elif rating:
            # Debug: Why no reviews if we have a rating?
            # Find the rating in text and show surrounding context
            idx = inner_text.find(rating)
            context = inner_text[max(0, idx-50):idx+100].replace("\n", " ")
            logger.info(f"  [MISSING REVIEWS] {pid}: {rating} | Context: ...{context}...")

    logger.info("-" * 30)
    logger.info(f"Results: {stats}")

if __name__ == "__main__":
    test_witnesses("roadmap")
