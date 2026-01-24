import yaml
import logging
from pathlib import Path
from rich.console import Console
from rich.progress import Progress

# Setup logging and console
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("audit")
console = Console()

def get_data_home():
    import os
    return Path(os.getenv("COCLI_DATA_HOME", str(Path.home() / ".local" / "share" / "data")))

def audit_campaign(campaign_name: str):
    data_home = get_data_home()
    companies_dir = data_home / "companies"
    campaign_dir = data_home / "campaigns" / campaign_name
    
    if not campaign_dir.exists():
        console.print(f"[red]Error: Campaign directory not found at {campaign_dir}[/red]")
        return

    # 1. Load Prospect Index (The "Source of Truth" for what SHOULD be in the campaign)
    # We'll look at the prospects directory for this campaign
    prospects_index_dir = campaign_dir / "indexes" / "google_maps_prospects"
    if not prospects_index_dir.exists():
        console.print(f"[yellow]Warning: No prospect index found at {prospects_index_dir}[/yellow]")
    else:
        # Each file in this dir is {place_id}.csv
        # We need the slugs. For now, let's assume the company folders exist.
        # A more robust way is to read the CSVs, but let's start with the folders.
        pass

    # Actually, let's just find every company folder that has the campaign name in its tags.lst
    console.print(f"[bold]Auditing companies for campaign: {campaign_name}[/bold]")
    
    company_folders = list(companies_dir.iterdir())
    tagged_count = 0
    fixed_count = 0
    email_count = 0

    with Progress() as progress:
        task = progress.add_task("[cyan]Processing companies...", total=len(company_folders))
        
        for folder in company_folders:
            progress.update(task, advance=1)
            if not folder.is_dir():
                continue
                
            tags_file = folder / "tags.lst"
            index_file = folder / "_index.md"
            
            if not tags_file.exists() or not index_file.exists():
                continue
                
            # Read tags from tags.lst
            tags = set(tags_file.read_text().strip().split('\n'))
            
            if campaign_name in tags:
                tagged_count += 1
                
                # Check if it's in the YAML index
                try:
                    content = index_file.read_text()
                    parts = content.split('---')
                    if len(parts) < 3:
                        continue
                        
                    data = yaml.safe_load(parts[1]) or {}
                    yaml_tags = data.get('tags', [])
                    if isinstance(yaml_tags, str):
                        yaml_tags = [yaml_tags]
                    
                    # Update YAML if campaign tag is missing
                    if campaign_name not in yaml_tags:
                        yaml_tags.append(campaign_name)
                        if 'prospect' not in yaml_tags:
                            yaml_tags.append('prospect')
                        
                        data['tags'] = yaml_tags
                        
                        # Write back
                        new_content = "---" + "\n" + yaml.dump(data, sort_keys=False) + "---" + "\n"
                        index_file.write_text(new_content)
                        fixed_count += 1
                    
                    if data.get('email'):
                        email_count += 1
                        
                except Exception as e:
                    logger.error(f"Error processing {folder.name}: {e}")

    console.print(f"\n[bold green]Audit Complete for {campaign_name}:[/bold green]")
    console.print(f"  • Companies with '{campaign_name}' in tags.lst: [bold]{tagged_count}[/bold]")
    console.print(f"  • Companies where YAML tags were missing and FIXED: [bold]{fixed_count}[/bold]")
    console.print(f"  • Total Enriched Emails found in these companies: [bold]{email_count}[/bold]")
    console.print("\n[dim]Note: Run 'make report' now to see the updated numbers.[/dim]")

if __name__ == "__main__":
    import sys
    camp = sys.argv[1] if len(sys.argv) > 1 else "turboship"
    audit_campaign(camp)
