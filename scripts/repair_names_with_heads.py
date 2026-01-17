import asyncio
import yaml
from pathlib import Path
from typing import List
from rich.console import Console
from rich.progress import track

from cocli.core.config import get_companies_dir, get_campaign
from cocli.scrapers.head_scraper import HeadScraper
from cocli.compilers.website_compiler import WebsiteCompiler

console = Console()

async def audit_and_fix_heads(campaign_name: str, target_slug: Optional[str] = None) -> None:
    companies_dir = get_companies_dir()
    targets: List[Path] = []
    
    if target_slug:
        company_dir = companies_dir / target_slug
        if company_dir.is_dir():
            targets.append(company_dir)
        else:
            console.print(f"[red]Company slug {target_slug} not found.[/red]")
            return
    else:
        # 1. Identify suspicious companies
        console.print(f"[bold blue]Auditing companies in campaign '{campaign_name}'...[/bold blue]")
        
        for company_dir in track(list(companies_dir.iterdir()), description="Auditing..."):
        if not company_dir.is_dir():
            continue
            
        tags_file = company_dir / "tags.lst"
        if not tags_file.exists() or campaign_name not in tags_file.read_text():
            continue
            
        index_md = company_dir / "_index.md"
        if not index_md.exists():
            continue
            
        # Check for slug-based name
        try:
            content = index_md.read_text()
            parts = content.split("---")
            if len(parts) >= 3:
                data = yaml.safe_load(parts[1])
                name = data.get("name", "")
                slug = company_dir.name
                domain = data.get("domain", "")
                
                is_slug = name == slug or name == domain
                is_generic = name in ["N/A", "Home", "Gmail", "Currently.com", "403 Forbidden"]
                
                # Check for suspicious tech (contains flooring keywords)
                tech_stack = data.get("tech_stack", [])
                has_suspicious_tech = any("floor" in str(t).lower() for t in tech_stack)
                
                if is_slug or is_generic or has_suspicious_tech:
                    targets.append(company_dir)
        except Exception:
            continue

    console.print(f"[green]Found {len(targets)} suspicious companies requiring head-scrape.[/green]")
    
    if not targets:
        return

    # 2. Run High-Speed Head Scrape
    scraper = HeadScraper()
    compiler = WebsiteCompiler()
    
    for company_dir in track(targets, description="Repairing..."):
        index_md = company_dir / "_index.md"
        try:
            parts = index_md.read_text().split("---")
            data = yaml.safe_load(parts[1])
            domain = data.get("domain") or company_dir.name
            
            head_html, title = await scraper.fetch_head(domain)
            if head_html:
                # Update website.md
                enrich_path = company_dir / "enrichments" / "website.md"
                enrich_data = {}
                if enrich_path.exists():
                    e_content = enrich_path.read_text().split("---")
                    if len(e_content) >= 3:
                        enrich_data = yaml.safe_load(e_content[1])
                
                enrich_data["head_html"] = head_html
                if title:
                    enrich_data["title"] = title
                
                with open(enrich_path, "w") as f:
                    f.write("---")
                    yaml.dump(enrich_data, f)
                    f.write("---")
                
                # Save head.html
                with open(company_dir / "enrichments" / "head.html", "w") as f:
                    f.write(head_html)
                
                # Re-compile
                compiler.compile(company_dir)
                
        except Exception as e:
            console.print(f"[red]Failed to repair {company_dir.name}: {e}[/red]")

if __name__ == "__main__":
    import sys
    campaign = get_campaign()
    slug = None
    
    if len(sys.argv) > 1:
        # Check if first arg is a known campaign or a slug
        arg = sys.argv[1]
        campaign_dir = get_campaigns_dir() / arg
        if campaign_dir.exists():
            campaign = arg
            if len(sys.argv) > 2:
                slug = sys.argv[2]
        else:
            slug = arg
            
    if not campaign and not slug:
        print("Usage: python repair_names_with_heads.py [campaign] [slug]")
        sys.exit(1)
        
    asyncio.run(audit_and_fix_heads(campaign or "unknown", slug))
