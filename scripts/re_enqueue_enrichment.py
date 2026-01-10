import csv
import logging
from typing import Optional
import typer
from cocli.core.config import get_campaign_dir
from cocli.core.queue.factory import get_queue_manager
from cocli.models.queue import QueueMessage
from cocli.core.text_utils import slugify

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = typer.Typer()

def re_enqueue_enrichment(campaign_name: str, target_id: Optional[str] = None) -> None:
    # Use global config for queue type if not set in env
    
    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        raise ValueError(f"Campaign directory not found for {campaign_name}")
        
    prospects_dir = campaign_dir / "indexes" / "google_maps_prospects"
    
    if not prospects_dir.exists():
        logger.error(f"Prospects directory not found: {prospects_dir}")
        return

    enrich_queue = get_queue_manager("enrichment", use_cloud=False, queue_type="enrichment", campaign_name=campaign_name)
    
    enqueued = 0
    
    logger.info("Scanning prospects...")
    
    files_to_process = list(prospects_dir.glob("*.csv"))
    if target_id:
        # If target_id looks like a place_id or filename
        if not target_id.endswith(".csv"):
            target_file = prospects_dir / f"{target_id}.csv"
        else:
            target_file = prospects_dir / target_id
            
        if target_file.exists():
            files_to_process = [target_file]
        else:
            # Maybe it's a domain or slug, we have to scan
            logger.info(f"Target '{target_id}' not a direct filename, searching...")

    for csv_file in files_to_process:
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                row = next(reader, None)
                if not row:
                    continue
                
                # Check for Domain and Name
                domain = row.get('Domain')
                name = row.get('Name')
                place_id = row.get('Place_ID')
                slug = slugify(name) if name else ""
                
                # If searching for target, check all potential matches
                if target_id:
                    match_found = (
                        target_id.lower() in [
                            domain.lower() if domain else "", 
                            slug.lower(), 
                            place_id.lower() if place_id else "", 
                            csv_file.stem.lower()
                        ]
                    )
                    if not match_found:
                        continue

                if domain and name:
                    msg = QueueMessage(
                        domain=domain,
                        company_slug=slug,
                        campaign_name=campaign_name,
                        ack_token=""
                    )
                    enrich_queue.push(msg)
                    enqueued += 1
                    logger.info(f"Enqueued: {name} ({domain})")
                    if target_id: # Found our single target
                        break
                    
                    if enqueued % 100 == 0:
                        logger.info(f"Enqueued {enqueued} prospects...")
        except Exception as e:
            logger.error(f"Error processing {csv_file}: {e}")

    logger.info(f"Finished. Enqueued {enqueued} for re-enrichment.")

@app.command()
def main(target_id: Optional[str] = None, campaign: Optional[str] = None) -> None:
    if not campaign:
        from cocli.core.config import get_campaign
        campaign = get_campaign()
    
    if not campaign:
        print("Error: No campaign specified")
        return
        
    re_enqueue_enrichment(campaign, target_id)

if __name__ == "__main__":
    app()