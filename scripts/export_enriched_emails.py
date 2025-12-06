import typer
import csv
import yaml
from rich.console import Console
from rich.progress import track
from cocli.core.config import get_companies_dir, get_campaign_dir, get_campaign_scraped_data_dir
from cocli.core.utils import slugify

app = typer.Typer()
console = Console()

@app.command()
def main(campaign_name: str) -> None:
    companies_dir = get_companies_dir()
    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        console.print(f"[bold red]Campaign '{campaign_name}' not found.[/bold red]")
        raise typer.Exit(1)
        
    export_dir = campaign_dir / "exports"
    export_dir.mkdir(exist_ok=True)
    output_file = export_dir / f"enriched_emails_{campaign_name}.csv"
    
    # Load slugs from campaign prospects.csv to filter
    prospects_csv = get_campaign_scraped_data_dir(campaign_name) / "prospects.csv"
    target_slugs = set()
    if prospects_csv.exists():
        with open(prospects_csv, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f)
            for row in reader:
                domain = row.get("Domain")
                if domain:
                    target_slugs.add(slugify(domain))
    
    console.print(f"Found {len(target_slugs)} targets in campaign prospects.")

    results = []
    
    # Iterate all companies
    # We list explicitly to get a count for track()
    company_paths = [p for p in companies_dir.iterdir() if p.is_dir()]
    
    for company_path in track(company_paths, description="Scanning companies..."):
        # Filter by campaign
        if target_slugs and company_path.name not in target_slugs:
            continue

        website_md = company_path / "enrichments" / "website.md"
        if not website_md.exists(): 
            continue
        
        try:
            # Parse YAML frontmatter
            content = website_md.read_text()
            if content.startswith("---"):
                parts = content.split("---")
                if len(parts) >= 3:
                    data = yaml.safe_load(parts[1])
                    
                    if not data: 
                        continue

                    email = data.get("email")
                    personnel = data.get("personnel", [])
                    
                    emails = set()
                    if email: 
                        emails.add(email)
                    
                    if personnel:
                        for p in personnel:
                            if isinstance(p, dict) and p.get("email"):
                                emails.add(p["email"])
                            elif isinstance(p, str) and "@" in p: # fallback
                                 emails.add(p)
                    
                    if emails:
                        results.append({
                            "company": data.get("company_name") or company_path.name,
                            "domain": data.get("domain") or company_path.name,
                            "emails": "; ".join(emails),
                            "phone": data.get("phone"),
                            "website": data.get("url")
                        })
        except Exception:
            pass

    with open(output_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["company", "domain", "emails", "phone", "website"])
        writer.writeheader()
        writer.writerows(results)
        
    console.print(f"[bold green]Exported {len(results)} companies with emails to {output_file}[/bold green]")

if __name__ == "__main__":
    app()
