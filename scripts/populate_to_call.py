import os
import sys
from pathlib import Path
from typing import Set, Dict, Any, List

# Ensure cocli is in the path
sys.path.append(os.getcwd())

from cocli.utils.usv_utils import USVReader
from cocli.models.campaigns.queues.to_call import ToCallTask
from cocli.core.constants import UNIT_SEP
from cocli.core.text_utils import extract_domain

def get_base_domain(url_or_domain: str) -> str:
    """Helper to get base domain (e.g. blog.example.com -> example.com)."""
    if not url_or_domain:
        return ""
    d = extract_domain(url_or_domain)
    if not d:
        if "." in url_or_domain and not url_or_domain.startswith("http"):
            d = url_or_domain
        else:
            return ""
    
    parts = d.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return d

def populate_to_call(campaign_name: str, count: int = 40) -> None:
    checkpoint_path = Path(f"data/campaigns/{campaign_name}/indexes/google_maps_prospects/prospects.checkpoint.usv")
    wal_dir = Path(f"data/campaigns/{campaign_name}/indexes/google_maps_prospects/wal")
    email_shards_dir = Path(f"data/campaigns/{campaign_name}/indexes/emails/shards")
    
    if not checkpoint_path.exists():
        print(f"Error: Checkpoint not found at {checkpoint_path}")
        return

    # 1. Load enriched domains (Companies with emails)
    print("Loading enriched email domains...")
    enriched_domains: Set[str] = set()
    if email_shards_dir.exists():
        for shard in email_shards_dir.glob("*.usv"):
            with open(shard, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split(UNIT_SEP)
                    if len(parts) >= 2:
                        # Extract domain from source URL (Index 1)
                        domain = get_base_domain(parts[1])
                        if domain:
                            enriched_domains.add(domain)
    print(f"Found {len(enriched_domains)} enriched unique base domains.")

    # 2. Collect all prospect files
    files_to_process = [checkpoint_path]
    if wal_dir.exists():
        files_to_process.extend(list(wal_dir.rglob("*.usv")))
    
    # 3. Find candidates
    candidates: List[Dict[str, Any]] = []
    seen_slugs: Set[str] = set()
    
    print("Gathering candidates...")
    for usv_file in files_to_process:
        with open(usv_file, "r", encoding="utf-8") as f:
            reader = USVReader(f)
            for row in reader:
                if len(row) < 26:
                    continue
                    
                slug = row[1]
                if slug in seen_slugs:
                    continue
                
                website = row[19]
                if not website:
                    continue
                    
                domain = get_base_domain(website)
                if not domain or domain not in enriched_domains:
                    continue
                    
                reviews_count_str = row[24]
                average_rating_str = row[25]
                
                try:
                    reviews_count = int("".join(filter(str.isdigit, reviews_count_str))) if reviews_count_str else 0
                    average_rating = float(average_rating_str.strip('"')) if average_rating_str else 0.0
                except (ValueError, TypeError):
                    continue
                
                score = average_rating * reviews_count
                
                candidates.append({
                    "slug": slug,
                    "name": row[2],
                    "domain": domain,
                    "score": score,
                    "rating": average_rating,
                    "reviews": reviews_count
                })
                seen_slugs.add(slug)

    # 4. Sort by score (Rating * Reviews) Descending
    candidates.sort(key=lambda x: x["score"], reverse=True)
    
    top_items = candidates[:count]
    print(f"Selected top {len(top_items)} prospects by social proof score.")

    # 5. Populate To Call queue
    for item in top_items:
        task = ToCallTask(
            campaign_name=campaign_name,
            company_slug=item["slug"],
            domain=item["domain"],
            priority=1,
            ack_token=None
        )
        task.save()
        print(f"  Enqueued: {item['name']} (Score: {item['score']:.1f})")

    print(f"Successfully enqueued {len(top_items)} items to the 'to-call' queue.")

if __name__ == "__main__":
    campaign_arg = sys.argv[1] if len(sys.argv) > 1 else "roadmap"
    populate_to_call(campaign_arg)
