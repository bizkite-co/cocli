import typer
import json
from rich.console import Console
from rich.table import Table
from pathlib import Path

from cocli.models.company import Company

app = typer.Typer()
console = Console()

@app.command()
def main(
    tag: str = typer.Argument("batch-v6-test-1", help="Tag used for the test batch."),
) -> None:
    """
    Evaluates the results of a re-scrape batch by checking how many prospects now have emails.
    """
    console.print(f"[bold]Evaluating results for batch tag: {tag}[/bold]")
    
    # Load enqueued reference if it exists
    ref_path = Path(f"enqueued_{tag}.json")
    enqueued_slugs = set()
    if ref_path.exists():
        enqueued_data = json.loads(ref_path.read_text())
        enqueued_slugs = {item["slug"] for item in enqueued_data}
        console.print(f"Found reference file with {len(enqueued_slugs)} prospects.")

    all_companies = Company.get_all()
    results = []
    
    found_email_count = 0
    total_batch_count = 0
    
    for company in all_companies:
        if tag in company.tags:
            total_batch_count += 1
            has_email = bool(company.email)
            if has_email:
                found_email_count += 1
            
            results.append({
                "name": company.name,
                "slug": company.slug,
                "domain": company.domain,
                "has_email": has_email,
                "email": company.email,
                "all_emails": company.all_emails,
                "tech_stack": company.tech_stack
            })

    if not results:
        console.print(f"[yellow]No companies found with tag: {tag}[/yellow]")
        return

    # Display Summary
    console.print("\n[bold underline]Batch Results Summary[/bold underline]")
    console.print(f"Total prospects in batch: {total_batch_count}")
    console.print(f"Prospects with new emails: [bold green]{found_email_count}[/bold green]")
    if total_batch_count > 0:
        success_rate = (found_email_count / total_batch_count) * 100
        console.print(f"Success Rate: [bold]{success_rate:.1f}%[/bold]")

    # Display Table of successes
    if found_email_count > 0:
        table = Table(title=f"Prospects with New Emails (Tag: {tag})")
        table.add_column("Name", style="cyan")
        table.add_column("Domain", style="magenta")
        table.add_column("Primary Email", style="green")
        table.add_column("Tech Stack", style="yellow")

        for r in results:
            if r["has_email"]:
                tech_stack = r["tech_stack"]
                tech_stack_str = ", ".join(tech_stack) if isinstance(tech_stack, list) else ""
                table.add_row(
                    str(r["name"]),
                    str(r["domain"]),
                    str(r["email"]),
                    tech_stack_str
                )
        
        console.print(table)
    else:
        console.print("\n[yellow]No new emails found in this batch yet. Processing may still be in progress.[/yellow]")

if __name__ == "__main__":
    app()
