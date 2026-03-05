# POLICY: frictionless-data-policy-enforcement
import logging
from cocli.core.paths import paths
from cocli.utils.usv_utils import USVReader

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("discovery_audit")

def audit_discovery(campaign_name: str) -> None:
    results_dir = paths.campaign(campaign_name).path / "queues" / "gm-list" / "completed" / "results"
    
    stats = {
        "total_records": 0,
        "with_rating": 0,
        "with_reviews": 0,
        "with_gmb_url": 0,
        "with_long_gmb_url": 0
    }
    
    logger.info(f"Auditing discovery results in: {results_dir}")
    
    # Discovery Trace Schema (9 fields):
    # 0: place_id, 1: slug, 2: name, 3: phone, 4: domain, 5: reviews, 6: rating, 7: address, 8: gmb_url
    for usv_file in results_dir.rglob("*.usv"):
        try:
            with open(usv_file, "r", encoding="utf-8") as f:
                reader = USVReader(f)
                for row in reader:
                    if len(row) >= 9:
                        stats["total_records"] += 1
                        
                        reviews = row[5].strip()
                        rating = row[6].strip()
                        url = row[8].strip()
                        
                        if rating:
                            stats["with_rating"] += 1
                        if reviews:
                            stats["with_reviews"] += 1
                        if url:
                            stats["with_gmb_url"] += 1
                            if len(url) > 100 and "place_id" not in url:
                                stats["with_long_gmb_url"] += 1
                                
        except Exception as e:
            logger.debug(f"Failed to read {usv_file}: {e}")

    logger.info("-" * 40)
    logger.info(f"Total Prospects Discovered: {stats['total_records']}")
    
    rating_pct = (stats["with_rating"] * 100 / max(1, stats["total_records"]))
    review_pct = (stats["with_reviews"] * 100 / max(1, stats["total_records"]))
    
    # Canary Thresholds
    RATINGS_GOAL = 60.0
    REVIEWS_GOAL = 40.0
    
    rating_status = "[PASS]" if rating_pct >= RATINGS_GOAL else "[FAIL]"
    review_status = "[PASS]" if review_pct >= REVIEWS_GOAL else "[FAIL]"

    logger.info(f"With Rating:               {stats['with_rating']} ({rating_pct:.1f}%) {rating_status}")
    logger.info(f"With Review Count:         {stats['with_reviews']} ({review_pct:.1f}%) {review_status}")
    logger.info(f"With GMB URL:              {stats['with_gmb_url']} ({stats['with_gmb_url']*100/max(1,stats['total_records']):.1f}%)")
    logger.info(f"With Long Canonical URL:   {stats['with_long_gmb_url']} ({stats['with_long_gmb_url']*100/max(1,stats['total_records']):.1f}%)")
    logger.info("-" * 40)
    
    if rating_pct < RATINGS_GOAL or review_pct < REVIEWS_GOAL:
        logger.warning(f"CANARY AUDIT FAILED: High-Fidelity coverage below thresholds (Ratings: {RATINGS_GOAL}%, Reviews: {REVIEWS_GOAL}%)")
        logger.warning("Potential 'Limited View' anti-bot detection active.")
    else:
        logger.info("CANARY AUDIT PASSED: High-Fidelity coverage meets quality standards.")

if __name__ == "__main__":
    audit_discovery("roadmap")
