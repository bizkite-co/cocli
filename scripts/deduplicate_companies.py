import typer
import logging
from rich.console import Console
from rich.progress import track
from cocli.core.config import get_companies_dir, get_campaign, get_campaigns_dir
from cocli.models.company import Company
from cocli.utils.usv_utils import USVDictWriter, USVDictReader
from pathlib import Path
from typing import Optional, List, Dict, Set
import shutil

app = typer.Typer()
console = Console()
logger = logging.getLogger(__name__)

@app.command()
def propose(
    campaign_name: Optional[str] = typer.Argument(None, help="Campaign context for matching (optional)."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="File to save proposed merges to.")
) -> None:
    """Identify duplicate companies and propose merges."""
    if not campaign_name:
        campaign_name = get_campaign()
    
    if campaign_name:
        campaign_dir = get_campaigns_dir() / campaign_name
        recovery_dir = campaign_dir / "recovery"
        if output is None:
            recovery_dir.mkdir(parents=True, exist_ok=True)
            output = recovery_dir / "proposed_company_merges.usv"
    else:
        if output is None:
            output = Path("proposed_company_merges.usv")

    # 1. Indexes for finding duplicates
    by_domain: Dict[str, List[str]] = {}
    by_place_id: Dict[str, List[str]] = {}
    by_hash: Dict[str, List[str]] = {}
    
    all_companies = list(Company.get_all())
    console.print(f"Scanning {len(all_companies)} companies...")

    junk_domains = {"gmail.com", "hotmail.com", "yahoo.com", "outlook.com", "aol.com", "icloud.com", "msn.com", "me.com", "live.com", "googlemail.com", "currently.com", "att.net", "comcast.net", "verizon.net", "sbcglobal.net"}

    for company in track(all_companies, description="Indexing..."):
        slug = company.slug
        if company.domain and company.domain.lower() not in junk_domains:
            by_domain.setdefault(company.domain.lower(), []).append(slug)
        if company.place_id:
            by_place_id.setdefault(company.place_id, []).append(slug)
        if company.company_hash:
            by_hash.setdefault(company.company_hash, []).append(slug)

    # 2. Identify duplicate groups
    dup_groups: List[Set[str]] = []
    
    def add_group(slugs: List[str]) -> None:
        if len(slugs) < 2:
            return
        slug_set = set(slugs)
        # Check if this group overlaps with any existing group
        for g in dup_groups:
            if not g.isdisjoint(slug_set):
                g.update(slug_set)
                return
        dup_groups.append(slug_set)

    # Only group by Place ID or Hash automatically
    for slugs in by_place_id.values():
        add_group(slugs)
    for slugs in by_hash.values():
        add_group(slugs)
    
    # For domains, only group if they ALSO have the same Place ID (or no Place ID)
    for domain, slugs in by_domain.items():
        if len(slugs) < 2:
            continue
        
        # Group slugs by Place ID within this domain
        p_groups: Dict[Optional[str], List[str]] = {}
        for s in slugs:
            c = Company.get(s)
            pid = c.place_id if c else None
            p_groups.setdefault(pid, []).append(s)
            
        for p_slugs in p_groups.values():
            add_group(p_slugs)

    proposed_merges = []
    
    for group in track(dup_groups, description="Analyzing duplicates..."):
        slug_list = sorted(list(group))
        all_objs = [Company.get(s) for s in slug_list]
        company_objs = [c for c in all_objs if c] # Filtered list of non-None Company objects
        
        if len(company_objs) < 2:
            continue
            
        # Determine "Winner"
        # Priority: 1. Has Place ID, 2. Has Domain, 3. Has more tags, 4. Longer name
        def score(c: Company) -> int:
            s = 0
            if c.place_id:
                s += 100
            if c.domain:
                s += 50
            s += len(c.tags) * 10
            s += len(c.name)
            return s
            
        winner = max(company_objs, key=score)
        
        for c in company_objs:
            if c.slug == winner.slug:
                continue
            
            proposed_merges.append({
                "winner_slug": winner.slug,
                "winner_name": winner.name,
                "loser_slug": c.slug,
                "loser_name": c.name,
                "reason": "Duplicate (Shared Domain/PlaceID/Hash)"
            })

    if proposed_merges:
        with open(output, 'w', encoding='utf-8') as f:
            writer = USVDictWriter(f, fieldnames=["winner_slug", "winner_name", "loser_slug", "loser_name", "reason"])
            for m in proposed_merges:
                writer.writerow(m)
        console.print(f"\n[bold green]Success![/bold green] Saved {len(proposed_merges)} proposed merges to [cyan]{output}[/cyan]")
    else:
        console.print("\nNo duplicates found.")

@app.command()
def apply(
    input_file: Path = typer.Argument(..., help="The USV file containing merges to apply.")
) -> None:
    """Apply the merges from a USV file."""
    if not input_file.exists():
        console.print(f"[bold red]Error:[/bold red] File {input_file} not found.")
        return

    applied_count = 0
    total_rows = 0
    companies_dir = get_companies_dir()
    
    with open(input_file, 'r', encoding='utf-8') as f:
        reader = USVDictReader(f, fieldnames=["winner_slug", "winner_name", "loser_slug", "loser_name", "reason"])
        
        for row in reader:
            total_rows += 1
            winner_slug = row["winner_slug"]
            loser_slug = row["loser_slug"]
            
            try:
                winner = Company.get(winner_slug)
                loser = Company.get(loser_slug)
                
                if winner and loser:
                    console.print(f"  [cyan]Merging:[/cyan] {loser_slug} -> {winner_slug}")
                    winner.merge_with(loser)
                    winner.save()
                    
                    # Delete the loser's directory
                    loser_dir = companies_dir / loser_slug
                    if loser_dir.exists():
                        shutil.rmtree(loser_dir)
                        console.print(f"  [red]Deleted:[/red] {loser_slug}")
                    
                    applied_count += 1
                else:
                    if not winner:
                        console.print(f"  [red]Error:[/red] Winner {winner_slug} not found.")
                    if not loser:
                        console.print(f"  [red]Error:[/red] Loser {loser_slug} not found.")
            except Exception as e:
                console.print(f"  [red]Error merging {loser_slug} into {winner_slug}:[/red] {e}")

    console.print(f"\n[bold green]Finished![/bold green] Applied {applied_count} merges out of {total_rows} rows.")

if __name__ == "__main__":
    app()
