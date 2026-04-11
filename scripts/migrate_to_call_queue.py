# POLICY: frictionless-data-policy-enforcement
import logging
from typing import Optional
from datetime import datetime, UTC

from cocli.models.companies.company import Company
from cocli.models.campaigns.queues.to_call import ToCallTask
from cocli.core.config import get_campaign, set_campaign
from cocli.core.paths import paths

logger = logging.getLogger(__name__)

def migrate_to_call_queue(campaign_name: str) -> None:
    """
    1. Scan all companies with legacy 'to-call' tag:
       - Create a durable USV marker in 'pending/'.
       - REMOVE the tag (decoupling).
    2. Migrate legacy JSON markers in 'scheduled/' to the new sharded USV structure.
    """
    set_campaign(campaign_name)
    print(f"--- MIGRATING TO-CALL QUEUE FOR CAMPAIGN: {campaign_name} ---")

    # Part 1: Convert tags to filesystem markers and decouple
    print("Converting legacy 'to-call' tags to filesystem queue...")
    count_pending = 0
    for company in Company.get_all():
        if "to-call" in company.tags:
            task = ToCallTask(
                company_slug=company.slug,
                domain=company.domain or "unknown",
                campaign_name=campaign_name,
                ack_token=None
            )
            task_path = task.get_local_path()
            if not task_path.exists():
                task.save()
                count_pending += 1
                print(f"  [PENDING] Created USV marker for: {company.slug}")
            
            # Remove legacy tag
            company.tags.remove("to-call")
            company.save()
            print(f"  [DECOUPLED] Removed tag from: {company.slug}")

    # Part 2: Migrate scheduled items from legacy JSON to new sharded USV
    print("\nChecking legacy 'scheduled' JSON markers...")
    legacy_sched_dir = paths.campaign(campaign_name).path / "queues" / "to-call" / "scheduled"
    if not legacy_sched_dir.exists():
        print("  No scheduled directory found.")
        return

    count_scheduled = 0
    # The old structure was scheduled/{YYYY-MM-DD}/{slug}.json
    for entry in legacy_sched_dir.iterdir():
        # Handle the old flat date folders (YYYY-MM-DD)
        if entry.is_dir() and len(entry.name) == 10: 
            try:
                # Validate it's a date
                cb_date = datetime.strptime(entry.name, "%Y-%m-%d").replace(tzinfo=UTC)
                
                # Migrate each JSON file in this folder
                for json_file in entry.glob("*.json"):
                    slug = json_file.stem
                    company_obj: Optional[Company] = Company.get(slug)
                    if not company_obj:
                        print(f"  [WARN] Company {slug} not found, skipping scheduled migration.")
                        continue
                    
                    # Create new sharded task
                    new_task = ToCallTask(
                        company_slug=slug,
                        domain=company_obj.domain or "unknown",
                        campaign_name=campaign_name,
                        callback_at=cb_date,
                        ack_token=None
                    )
                    
                    # Save new USV
                    new_task.save()
                    
                    # Remove old JSON
                    json_file.unlink()
                    count_scheduled += 1
                    print(f"  [SCHEDULED] Migrated {slug} to sharded USV for {entry.name}")

                # Clean up empty date folder
                if not any(entry.iterdir()):
                    entry.rmdir()

            except ValueError:
                continue

    print(f"\nMigration Complete for {campaign_name}:")
    print(f"- Converted {count_pending} tags to filesystem pending tasks.")
    print(f"- Migrated {count_scheduled} legacy scheduled tasks to sharded USV.")

if __name__ == "__main__":
    campaign = get_campaign() or "roadmap"
    migrate_to_call_queue(campaign)
    if campaign != "turboship": 
        migrate_to_call_queue("turboship")
