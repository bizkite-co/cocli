import typer
from typing import Optional
from rich.console import Console
from cocli.core.config import get_campaign, get_companies_dir
from cocli.core.prospects_csv_manager import ProspectsIndexManager
from cocli.core.text_utils import slugify

app = typer.Typer()
console = Console()

@app.command()
def main(campaign_name: Optional[str] = typer.Argument(None, help="Campaign name.")) -> None:
    if not campaign_name:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[bold red]Error: No campaign specified.[/bold red]")
        raise typer.Exit(1)

    companies_dir = get_companies_dir()
    manager = ProspectsIndexManager(campaign_name)
    
    enriched_count = 0
    emails_found_count = 0
    not_compiled_but_has_email = 0
    total_prospects = 0
    
    console.print(f"Analyzing stats for campaign: [bold cyan]{campaign_name}[/bold cyan]...")

    for prospect in manager.read_all_prospects():
        total_prospects += 1
        slugs_to_check = []
        if prospect.company_slug:
            slugs_to_check.append(prospect.company_slug)
        if prospect.name:
            slugs_to_check.append(slugify(prospect.name))
        if prospect.domain:
            slugs_to_check.append(slugify(prospect.domain))
            
        for slug in set(slugs_to_check):
            company_path = companies_dir / slug
            if (company_path / "enrichments" / "website.md").exists():
                enriched_count += 1
                
                has_email_in_index = False
                index_path = company_path / "_index.md"
                if index_path.exists():
                    try:
                        content = index_path.read_text()
                        if "email: " in content and "email: null" not in content and "email: ''" not in content:
                            emails_found_count += 1
                            has_email_in_index = True
                    except Exception:
                        pass
                
                if not has_email_in_index:
                    # Check website.md
                    web_path = company_path / "enrichments" / "website.md"
                    if web_path.exists():
                        web_content = web_path.read_text()
                        if "email: " in web_content and "email: null" not in web_content and "email: ''" not in web_content:
                            not_compiled_but_has_email += 1
                break
    
    console.print(f"Total Prospects in Index: [bold]{total_prospects}[/bold]")
    console.print(f"Enriched: [bold]{enriched_count}[/bold]")
    console.print(f"Emails Found (in _index.md): [bold green]{emails_found_count}[/bold green]")
    console.print(f"Emails Found in website.md but NOT in _index.md: [bold yellow]{not_compiled_but_has_email}[/bold yellow]")

if __name__ == "__main__":
    app()
