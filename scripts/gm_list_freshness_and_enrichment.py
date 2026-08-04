"""Read-only report on gm-list discovery output: freshness (completed_at per
result file) and downstream enrichment coverage (email/keywords via Company).

gm-list/completed/results/**/*.usv holds the list-discovery output
(GoogleMapsListItem shape: place_id, company_slug, name, category, phone,
domain, reviews_count, average_rating, street_address, gmb_url) - each file
has a sibling .json task record with completed_at/worker_id/result_count.

This answers: how much of what gm-list actually discovered has since been
enriched (emails/keywords), independent of whatever happened downstream in
gm-details/compaction.
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from cocli.core.paths import paths
from cocli.models.companies.company import Company
from cocli.utils.usv_utils import USVDictReader

FIELDS = [
    "place_id", "company_slug", "name", "category", "phone", "domain",
    "reviews_count", "average_rating", "street_address", "gmb_url",
]


def load_gm_list_results(results_dir: Path) -> dict[str, dict]:
    """place_id -> {row fields..., completed_at, worker_id}. Last-seen wins
    on duplicate place_id across files (by completed_at)."""
    by_pid: dict[str, dict] = {}
    usv_files = sorted(results_dir.rglob("*.usv"))
    for usv_path in usv_files:
        json_path = usv_path.with_suffix(".json")
        completed_at = None
        worker_id = None
        if json_path.exists():
            try:
                meta = json.loads(json_path.read_text())
                completed_at = meta.get("completed_at")
                worker_id = meta.get("worker_id")
            except Exception:
                pass
        try:
            with open(usv_path, "r", encoding="utf-8") as f:
                reader = USVDictReader(f, fieldnames=FIELDS)
                for row in reader:
                    pid = row.get("place_id")
                    if not pid:
                        continue
                    existing = by_pid.get(pid)
                    if existing is None or (completed_at or "") > (existing.get("completed_at") or ""):
                        row["completed_at"] = completed_at
                        row["worker_id"] = worker_id
                        row["source_file"] = str(usv_path)
                        by_pid[pid] = row
        except Exception as e:
            print(f"  skip {usv_path}: {e}")
    return by_pid


def main(campaign: str, since: str | None) -> None:
    results_dir = paths.queue(campaign, "gm-list") / "completed" / "results"
    by_pid = load_gm_list_results(results_dir)
    print(f"Total distinct place_ids in gm-list completed results: {len(by_pid)}")

    dated = [r for r in by_pid.values() if r.get("completed_at")]
    print(f"Rows with a completed_at timestamp: {len(dated)}")
    if dated:
        oldest = min(r["completed_at"] for r in dated)
        newest = max(r["completed_at"] for r in dated)
        print(f"completed_at range: {oldest}  ..  {newest}")

    if since:
        by_pid = {p: r for p, r in by_pid.items() if (r.get("completed_at") or "") >= since}
        print(f"After filtering to completed_at >= {since}: {len(by_pid)} place_ids")

    has_category = sum(1 for r in by_pid.values() if r.get("category"))
    has_rating = sum(1 for r in by_pid.values() if r.get("average_rating"))
    print(f"With category: {has_category} ({has_category*100//max(len(by_pid),1)}%)")
    print(f"With rating:   {has_rating} ({has_rating*100//max(len(by_pid),1)}%)")

    # Enrichment coverage via Company record for the same slug
    enriched_email = 0
    enriched_keywords = 0
    company_missing = 0
    for r in by_pid.values():
        slug = r.get("company_slug")
        c = Company.get(slug) if slug else None
        if c is None:
            company_missing += 1
            continue
        if c.email or c.all_emails:
            enriched_email += 1
        if c.keywords:
            enriched_keywords += 1

    n = len(by_pid)
    print(f"\nCompany record missing entirely: {company_missing} ({company_missing*100//max(n,1)}%)")
    print(f"Company has email/all_emails:     {enriched_email} ({enriched_email*100//max(n,1)}%)")
    print(f"Company has keywords:             {enriched_keywords} ({enriched_keywords*100//max(n,1)}%)")

    worker_counts = Counter(r.get("worker_id") for r in by_pid.values())
    print("\nBy worker_id:", dict(worker_counts))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", nargs="?", default="turboship")
    parser.add_argument("--since", default=None, help="ISO timestamp filter, e.g. 2026-06-28")
    args = parser.parse_args()
    main(args.campaign, args.since)
