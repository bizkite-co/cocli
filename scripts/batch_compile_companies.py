import logging
import typer
from rich.console import Console
from cocli.core.config import get_companies_dir, load_campaign_config
from cocli.compilers.website_compiler import WebsiteCompiler

from typing import Optional

app = typer.Typer()
console = Console()

def batch_compile(campaign_name: str, company_slug: Optional[str] = None) -> None:
    companies_dir = get_companies_dir()
    config = load_campaign_config(campaign_name)
    tag = config.get('campaign', {}).get('tag') or campaign_name
    
    compiler = WebsiteCompiler()
    
    if company_slug:
        company_paths = [companies_dir / company_slug]
    else:
        company_paths = [p for p in companies_dir.iterdir() if p.is_dir()]
        
    updated_count = 0
    total_count = 0
    
    console.print(f"Starting compile for tag: [bold]{tag}[/bold]")
    
    for company_path in company_paths:
        if not company_path.exists():
            continue
            
        # Filter by tag
        tags_file = company_path / "tags.lst"
        if not tags_file.exists():
            continue
            
        try:
            tags = tags_file.read_text().splitlines()
            if tag not in [t.strip() for t in tags]:
                continue
        except Exception:
            continue
            
        total_count += 1
        try:
            compiler.compile(company_path)
            updated_count += 1
        except Exception as e:
            console.print(f"[red]Failed to compile {company_path.name}: {e}[/red]")

    compiler.save_audit_report()
    console.print(f"Finished. Processed {total_count} companies.")

@app.command()
def run(
    campaign: str = typer.Argument(..., help="Campaign name."),
    company: Optional[str] = typer.Option(None, "--company", "-c", help="Specific company slug or comma-separated slugs to compile.")
) -> None:
    if company and "," in company:
        slugs = [s.strip() for s in company.split(",")]
        for slug in slugs:
            batch_compile(campaign, slug)
    else:
        batch_compile(campaign, company)

if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    app()