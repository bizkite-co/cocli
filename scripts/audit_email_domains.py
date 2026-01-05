import typer
import json
from rich.console import Console
from rich.progress import track
from cocli.core.config import get_campaign_dir

app = typer.Typer()
console = Console()

COMMON_TLDS = {
    "online", "store", "group", "media", "design", "center", "repair", 
    "service", "system", "cleaning", "construction", "global", "solutions",
    "network", "support", "travel", "agency", "company", "studio", "today", "guide"
}

@app.command()
def main(campaign_name: str = "turboship", output_file: str = "suspicious_domains.json") -> None:
    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        console.print(f"[red]Campaign directory not found for: {campaign_name}[/red]")
        raise typer.Exit(1)
        
    email_index_dir = campaign_dir / "indexes" / "emails"
    
    if not email_index_dir.exists():
        console.print(f"[red]Email index directory not found: {email_index_dir}[/red]")
        raise typer.Exit(1)

    suspicious_entries = []
    
    console.print(f"Scanning email domains in: {email_index_dir}")

    # Collect all domain directories
    domain_dirs = [d for d in email_index_dir.iterdir() if d.is_dir()]
    
    for domain_dir in track(domain_dirs, description="Auditing domains..."):
        domain = domain_dir.name
        
        parts = domain.split('.')
        is_suspicious = False
        reason = ""

        if len(parts) < 2:
            is_suspicious = True
            reason = "No TLD"
        else:
            tld = parts[-1]
            # Heuristic: TLD > 4 chars and not in common list, OR contains uppercase
            if (len(tld) > 4 and tld.lower() not in COMMON_TLDS) or any(c.isupper() for c in tld):
                is_suspicious = True
                reason = f"Suspicious TLD ({tld})"
            
            # Check for uppercase in the domain body too, indicative of concatenation like "ExampleCom"
            if any(c.isupper() for c in domain):
                 is_suspicious = True
                 reason = "Contains Uppercase"

        if is_suspicious:
            # Get details from the first JSON file in the directory
            sample_file = next(domain_dir.glob("*.json"), None)
            if sample_file:
                try:
                    with open(sample_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        
                    entry = {
                        "domain": domain,
                        "reason": reason,
                        "email": data.get("email"),
                        "source": data.get("source"), # The URL where we found it
                        "file_path": str(sample_file)
                    }
                    suspicious_entries.append(entry)
                except Exception as e:
                    console.print(f"[red]Error reading {sample_file}: {e}[/red]")

    # Save to file
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(suspicious_entries, f, indent=2)

    console.print(f"[green]Found {len(suspicious_entries)} suspicious domains.[/green]")
    console.print(f"Results saved to: [bold]{output_file}[/bold]")

if __name__ == "__main__":
    app()
