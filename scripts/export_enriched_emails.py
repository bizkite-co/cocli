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
    checkpoint_path = prospect_manager.checkpoint_path

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
            ignore_errors=True,
            quote=''
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

    # Scraper artifacts occasionally land image filenames in the email column
    # (e.g. "..._580x@2x.png") - the "@2x" retina suffix looks like a valid
    # local-part@domain shape to a naive check, so filter on plausible email
    # shape AND reject image-extension "domains" explicitly.
    con.execute(r"""
        DELETE FROM emails
        WHERE NOT regexp_matches(email, '^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$')
           OR regexp_matches(lower(email), '\.(png|jpe?g|gif|webp|bmp|svg|ico|tiff?)$')
    """)

    # Email domains are frequently stored as full URLs (e.g.
    # "https://www.foo.com/") while prospect domains are bare hostnames
    # ("foo.com") - normalize both sides before joining or the match rate
    # silently undercounts.
    con.execute("ALTER TABLE emails ADD COLUMN norm_domain VARCHAR")
    con.execute(r"""
        UPDATE emails SET norm_domain = regexp_replace(regexp_replace(lower(domain), '^https?://(www\.)?', ''), '/$', '')
    """)
    con.execute("ALTER TABLE prospects ADD COLUMN norm_domain VARCHAR")
    con.execute(r"""
        UPDATE prospects SET norm_domain = regexp_replace(regexp_replace(lower(domain), '^https?://(www\.)?', ''), '/$', '')
    """)

    # 3. Perform High-Performance Join
    # We group emails by domain/slug to get a semicolon-separated list
    query = """
        SELECT
            p.name,
            COALESCE(p.domain, p.slug) as domain,
            string_agg(DISTINCT e.email, '; ') as emails,
            p.phone as phone,
            p.city,
            p.state,
            p.keyword as tag,
            p.category as category,
            p.first_category as first_category,
            p.place_id,
            p.slug,
            p.average_rating,
            p.reviews_count
        FROM prospects p
        LEFT JOIN emails e ON (
            p.norm_domain = e.norm_domain OR
            p.slug = e.company_slug OR
            p.slug = e.norm_domain OR
            p.norm_domain = e.company_slug
        )
        GROUP BY p.name, p.domain, p.slug, p.phone, p.city, p.state, p.keyword, p.category, p.first_category, p.place_id, p.average_rating, p.reviews_count
    """

    # Client report criteria: contactable leads only - phone, email, and a
    # category or keyword signal for outreach personalization.
    having_clauses = ["phone IS NOT NULL", "TRIM(phone) != ''"]
    if not include_all:
        having_clauses.append("emails IS NOT NULL")
    query += " HAVING " + " AND ".join(having_clauses)

    rows = con.execute(query).fetchall()

    results = []
    skipped_count = 0

    for row in track(rows, description="Refining leads..."):
        name, domain, emails, phone, city, state, keyword, category, first_category, place_id, slug, rating, reviews = row

        if exclusion_manager.is_excluded(domain=domain, slug=slug):
            continue

        # Load extra data from company files for enrichment-found keywords.
        website_data = get_website_data(slug) if slug else None
        found_keywords = website_data.found_keywords if website_data else []

        report_category = category or first_category or ""
        has_category_or_keywords = bool(report_category) or bool(found_keywords)

        if keywords and not found_keywords:
            continue
        if not has_category_or_keywords:
            skipped_count += 1
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
            "categories": report_category,
            "services": "",
            "products": "",
            "tags": "; ".join(filter(None, [keyword] + found_keywords)),
            "gmb_url": f"https://www.google.com/maps/search/?api=1&query=google&query_place_id={place_id}" if place_id else "",
            "rating": rating,
            "reviews": reviews
        })

    # 4. Write Output
    fieldnames = ["company", "domain", "emails", "phone", "website", "city", "state", "categories", "services", "products", "tags", "gmb_url", "rating", "reviews"]

    # 4a. Canonical USV (Frictionless data standard - authoritative artifact)
    output_file_usv = output_file.with_suffix(".usv")
    with open(output_file_usv, "w", newline="", encoding="utf-8") as f:
        from cocli.models.wal.record import US
        f.write(US.join(fieldnames) + "\n")
        for res in results:
            line = [str(res[name]) for name in fieldnames]
            f.write(US.join(line) + "\n")

    # 4b. Client-facing CSV rendered from the same result set (used by the
    # dashboard download button and on-page prospect cards).
    output_file_csv = output_file.with_suffix(".csv")
    import csv
    with open(output_file_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for res in results:
            writer.writerow(res)

    console.print("\n[bold green]Success![/bold green]")
    console.print(f"Exported: [bold]{len(results)}[/bold] companies")
    if skipped_count:
        console.print(f"Skipped: [bold red]{skipped_count}[/bold red] records without phone/category/keyword signal (check log)")
    console.print(f"Output: [cyan]{output_file_usv}[/cyan]")
    console.print(f"Output: [cyan]{output_file_csv}[/cyan]")

    # Also upload both artifacts to S3. The CSV is the one the dashboard
    # download button and on-page prospect fetch consume, so it needs a
    # proper text/csv content-type and an attachment disposition or the
    # browser won't offer a real "Save As" download for it.
    from cocli.core.reporting import get_boto3_session, load_campaign_config
    config = load_campaign_config(campaign_name)
    s3_config = config.get("aws", {})
    bucket_name = s3_config.get("cocli_web_bucket_name") or "cocli-web-assets-turboheat-net"

    try:
        session = get_boto3_session(config)
        s3 = session.client("s3")
        s3.upload_file(str(output_file_usv), bucket_name, f"exports/{campaign_name}-emails.usv")
        s3.upload_file(
            str(output_file_csv),
            bucket_name,
            f"exports/{campaign_name}-emails.csv",
            ExtraArgs={
                "ContentType": "text/csv",
                "ContentDisposition": f'attachment; filename="{campaign_name}-emails.csv"',
                "CacheControl": "no-cache, must-revalidate",
            },
        )
        console.print("[bold green]Successfully uploaded USV and CSV exports to S3.[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Failed to upload to S3: {e}[/bold red]")

if __name__ == "__main__":
    app()