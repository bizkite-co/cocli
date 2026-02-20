import typer
import yaml
from typing import Optional
from datetime import datetime
from pathlib import Path
import logging

from rich.console import Console
from rich.progress import track
from cocli.core.config import get_companies_dir, get_campaign
from cocli.models.companies.website import Website
from cocli.core.exclusions import ExclusionManager

app = typer.Typer()
console = Console()

def setup_export_logging(campaign_name: str) -> Path:
    logs_dir = Path(".logs")
    logs_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = logs_dir / f"export_emails_{campaign_name}_{timestamp}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(log_file)],
        force=True
    )
    # Also silence the standard cocli logger to terminal
    for logger_name in ["cocli.models.companies.company", "root"]:
        lgr = logging.getLogger(logger_name)
        lgr.setLevel(logging.ERROR)
        lgr.propagate = False
        lgr.addHandler(logging.FileHandler(log_file))
        
    return log_file

def get_website_data(company_slug: str) -> Optional[Website]:
    """Helper to load the website.md data for a company."""
    website_md_path = get_companies_dir() / company_slug / "enrichments" / "website.md"
    if not website_md_path.exists():
        return None
    
    try:
        content = website_md_path.read_text()
        # Extract YAML frontmatter
        from cocli.core.text_utils import parse_frontmatter
        frontmatter_str = parse_frontmatter(content)
        if frontmatter_str:
            data = yaml.safe_load(frontmatter_str)
            
            # Hotfix for legacy/malformed personnel data
            if data and "personnel" in data and isinstance(data["personnel"], list):
                sanitized_personnel = []
                for p in data["personnel"]:
                    if isinstance(p, str):
                        sanitized_personnel.append({"raw_entry": p})
                    elif isinstance(p, dict):
                        sanitized_personnel.append(p)
                data["personnel"] = sanitized_personnel

            if data:
                return Website.model_validate(data)
    except Exception:
        pass
    return None

@app.command()
def main(
    campaign_name: Optional[str] = typer.Argument(None, help="Campaign name. Defaults to current context."),
    keywords: bool = typer.Option(False, "--keywords", help="Only export companies that have found keywords (enriched)."),
    include_all: bool = typer.Option(False, "--all", "-a", help="Include all prospects even if they have no emails.")
) -> None:
    if not campaign_name:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[bold red]Error: No campaign specified and no active context.[/bold red]")
        raise typer.Exit(1)

    log_file = setup_export_logging(campaign_name)
    console.print(f"Exporting leads for [bold]{campaign_name}[/bold]")
    console.print(f"Detailed logs: [cyan]{log_file}[/cyan]")

    exclusion_manager = ExclusionManager(campaign_name)
    
    from cocli.core.config import get_campaign_exports_dir
    export_dir = get_campaign_exports_dir(campaign_name)
    output_file = export_dir / f"enriched_emails_{campaign_name}.csv"
    
    import duckdb
    con = duckdb.connect(database=':memory:')

    # 1. Load Prospects using DuckDB (FIMC Checkpoint)
    from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
    import json
    
    # Generate columns for DuckDB from model fields
    model_fields = GoogleMapsProspect.model_fields
    columns = {}
    for name, field in model_fields.items():
        # Map Python types to DuckDB types
        field_type = "VARCHAR"
        type_str = str(field.annotation)
        if "int" in type_str:
            field_type = "INTEGER"
        elif "float" in type_str:
            field_type = "DOUBLE"
        columns[name] = field_type

    from cocli.core.prospects_csv_manager import ProspectsIndexManager
    prospect_manager = ProspectsIndexManager(campaign_name)
    checkpoint_path = prospect_manager.index_dir / "prospects.checkpoint.usv"
    
    if not checkpoint_path.exists():
        console.print("[bold red]Error: Prospects checkpoint not found. Run sync-prospects first.[/bold red]")
        raise typer.Exit(1)

    # Prospect Schema
    con.execute(f"""
        CREATE TABLE prospects AS SELECT * FROM read_csv('{checkpoint_path}', 
            delim='\x1f', 
            header=False,
            columns={json.dumps(columns)},
            auto_detect=False,
            ignore_errors=True
        )
    """)

    # 2. Load Emails using DuckDB (Sharded Index)
    from cocli.core.email_index_manager import EmailIndexManager
    email_manager = EmailIndexManager(campaign_name)
    email_shard_glob = str(email_manager.shards_dir / "*.usv")
    
    # Check if any shards exist
    if list(email_manager.shards_dir.glob("*.usv")):
        con.execute(f"""
            CREATE TABLE emails AS SELECT * FROM read_csv('{email_shard_glob}', 
                delim='\x1f', 
                header=False,
                columns={{
                    'email': 'VARCHAR',
                    'domain': 'VARCHAR',
                    'company_slug': 'VARCHAR',
                    'source': 'VARCHAR',
                    'found_at': 'VARCHAR',
                    'first_seen': 'VARCHAR',
                    'last_seen': 'VARCHAR',
                    'verification_status': 'VARCHAR',
                    'tags': 'VARCHAR'
                }}
            )
        """)
    else:
        # Create empty table if no emails yet
        con.execute("CREATE TABLE emails (email VARCHAR, domain VARCHAR, company_slug VARCHAR, tags VARCHAR, last_seen VARCHAR)")

    # 3. Perform High-Performance Join
    # We group emails by domain/slug to get a semicolon-separated list
    query = """
        SELECT 
            p.name,
            COALESCE(p.domain, p.company_slug) as domain,
            string_agg(DISTINCT e.email, '; ') as emails,
            p.phone as phone,
            p.city,
            p.state,
            p.keyword as tag,
            p.place_id,
            p.company_slug,
            p.average_rating,
            p.reviews_count
        FROM prospects p
        LEFT JOIN emails e ON (
            p.domain = e.domain OR 
            p.company_slug = e.company_slug OR 
            p.company_slug = e.domain OR 
            p.domain = e.company_slug
        )
        GROUP BY p.name, p.domain, p.company_slug, p.phone, p.city, p.state, p.keyword, p.place_id, p.average_rating, p.reviews_count
    """
    
    if not include_all:
        query += " HAVING emails IS NOT NULL"

    rows = con.execute(query).fetchall()
    
    results = []
    skipped_count = 0
    
    for row in track(rows, description="Refining leads..."):
        name, domain, emails, phone, city, state, keyword, place_id, slug, rating, reviews = row
        
        if exclusion_manager.is_excluded(domain=domain, slug=slug):
            continue

        # Load extra data from company files ONLY for keywords/details if requested
        website_data = get_website_data(slug)
        if keywords:
            if not website_data or not website_data.found_keywords:
                continue

        # Construct final record
        results.append({
            "company": name,
            "domain": domain,
            "emails": emails or "",
            "phone": phone,
            "website": domain,
            "city": city,
            "state": state,
            "categories": "", # Add back if needed from company files
            "services": "",
            "products": "",
            "tags": "; ".join(filter(None, [keyword] + (website_data.found_keywords if website_data else []))),
            "gmb_url": f"https://www.google.com/maps/search/?api=1&query=google&query_place_id={place_id}" if place_id else "",
            "rating": rating,
            "reviews": reviews
        })

    # 4. Write Output
    output_file_usv = output_file.with_suffix(".usv")
    with open(output_file_usv, "w", newline="", encoding="utf-8") as f:
        from cocli.models.wal.record import US
        # Header
        f.write(US.join(["company", "domain", "emails", "phone", "website", "city", "state", "categories", "services", "products", "tags", "gmb_url", "rating", "reviews"]) + "\n")
        for res in results:
            line = [
                str(res["company"]),
                str(res["domain"]),
                str(res["emails"]),
                str(res["phone"]),
                str(res["website"]),
                str(res["city"]),
                str(res["state"]),
                str(res["categories"]),
                str(res["services"]),
                str(res["products"]),
                str(res["tags"]),
                str(res["gmb_url"]),
                str(res["rating"]),
                str(res["reviews"])
            ]
            f.write(US.join(line) + "\n")
        
    console.print("\n[bold green]Success![/bold green]")
    console.print(f"Exported: [bold]{len(results)}[/bold] companies")
    if skipped_count:
        console.print(f"Skipped: [bold red]{skipped_count}[/bold red] malformed records (check log)")
    console.print(f"Output: [cyan]{output_file_usv}[/cyan]")

    # Also upload the USV to S3
    from cocli.core.reporting import get_boto3_session, load_campaign_config
    config = load_campaign_config(campaign_name)
    s3_config = config.get("aws", {})
    bucket_name = s3_config.get("cocli_web_bucket_name") or "cocli-web-assets-turboheat-net"
    
    try:
        session = get_boto3_session(config)
        s3 = session.client("s3")
        s3.upload_file(str(output_file_usv), bucket_name, f"exports/{campaign_name}-emails.usv")
        console.print("[bold green]Successfully uploaded USV export to S3.[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Failed to upload to S3: {e}[/bold red]")

if __name__ == "__main__":
    app()