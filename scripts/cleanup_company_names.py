import typer
import logging
from rich.console import Console
from cocli.core.config import get_companies_dir
from cocli.models.company import Company
from cocli.core.prospects_csv_manager import ProspectsIndexManager
from cocli.utils.usv_utils import USVDictWriter
from pathlib import Path
from typing import Optional
import re

app = typer.Typer()
console = Console()
logger = logging.getLogger(__name__)

GENERIC_NAMES = {
    "Home", "Home Page", "N/A", "Flooring Contractor", "Flooring", "Contractor", 
    "Gmail", "Currently.com", "403 Forbidden", "404 Not Found", "Facebook", 
    "Instagram", "dot.cards", "Brand", "Cart", "Log In", "Sign Up", "Welcome"
}

SEO_JUNK_PATTERNS = [
    r"near me",
    r"best financial",
    r"financial advisor in",
    r"servicing",
    r"flooring store",
    r"contractor in",
    r"flooring in",
    r"planning in",
    r"advisor in",
    r"luxury flooring",
    r"affordable flooring"
]

def is_junk(name: str) -> bool:
    if not name:
        return True
    if name in GENERIC_NAMES or len(name) < 4:
        return True
    
    n_lower = name.lower()
    for pattern in SEO_JUNK_PATTERNS:
        if re.search(pattern, n_lower):
            return True
    return False

@app.command()
def main(
    campaign_name: str = typer.Argument(..., help="Campaign name for prospect matching."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="File to save proposed fixes to."),
    include_all: bool = typer.Option(False, "--all", "-a", help="Scan all companies, ignoring tags.")
) -> None:
    from cocli.core.config import get_campaigns_dir
    campaign_dir = get_campaigns_dir() / campaign_name
    recovery_dir = campaign_dir / "recovery"
    
    if output is None:
        recovery_dir.mkdir(parents=True, exist_ok=True)
        output = recovery_dir / "proposed_name_fixes.usv"

    companies_dir = get_companies_dir()
    prospects_manager = ProspectsIndexManager(campaign_name)
    
    # 1. Load all known identifiers for this campaign from its prospect index
    target_place_ids = set()
    target_slugs = set()
    place_id_names = {}
    
    for prospect in prospects_manager.read_all_prospects():
        if prospect.place_id:
            target_place_ids.add(prospect.place_id)
            if prospect.name:
                place_id_names[prospect.place_id] = prospect.name
        if prospect.company_slug:
            target_slugs.add(prospect.company_slug)

    proposed_fixes = []
    total_count = 0
    generic_count = 0

    console.print(f"Scanning companies (Campaign context: {campaign_name}, All: {include_all})")

    for company in Company.get_all():
        # A company belongs to this campaign if:
        # 1. It has the campaign tag
        # 2. OR its Place ID is in the campaign's prospect index
        # 3. OR its slug is in the campaign's prospect index
        in_campaign = (
            (campaign_name in company.tags) or 
            (company.place_id and company.place_id in target_place_ids) or
            (company.slug in target_slugs)
        )

        if not include_all and not in_campaign:
            continue
            
        total_count += 1
        current_name = company.name
        
        # Determine if current name is generic, slug-based, or SEO junk
        is_slug_based = current_name == company.slug or (company.domain and current_name == company.domain)
        
        if is_junk(current_name) or is_slug_based:
            generic_count += 1
            original_name = current_name
            new_name = None

            # Attempt 1: Get from Place ID index (Maps is highest quality)
            if company.place_id in place_id_names:
                candidate = place_id_names[company.place_id]
                if not is_junk(candidate):
                    new_name = candidate

            # Attempt 2: Use Website Title logic
            if not new_name or is_junk(new_name):
                website_md = companies_dir / company.slug / "enrichments" / "website.md"
                if website_md.exists():
                    try:
                        from cocli.core.text_utils import parse_frontmatter
                        import yaml
                        content = website_md.read_text()
                        frontmatter_str = parse_frontmatter(content)
                        if frontmatter_str:
                            data = yaml.safe_load(frontmatter_str) or {}
                            website_title = data.get("title") or data.get("company_name")
                            
                            if website_title:
                                # Try full title first if it's not super long
                                if len(website_title) < 50 and not is_junk(website_title):
                                    new_name = website_title
                                else:
                                    # Fallback to splitting
                                    parts = []
                                    if " | " in website_title:
                                        parts = [p.strip() for p in website_title.split(" | ")]
                                    elif " - " in website_title:
                                        parts = [p.strip() for p in website_title.split(" - ")]
                                    
                                    for part in reversed(parts): # Usually brand is at the end
                                        if not is_junk(part):
                                            new_name = part
                                            break
                                    
                                    if not new_name and parts and not is_junk(parts[0]):
                                        new_name = parts[0]

                            # Attempt 3: Extract from description if still junk
                            if (not new_name or is_junk(new_name)) and data.get("description"):
                                desc = data["description"]
                                if "officially changed our name to" in desc:
                                    match = re.search(r"officially changed our name to ([^.]+)", desc)
                                    if match:
                                        candidate = match.group(1).strip()
                                        if not is_junk(candidate):
                                            new_name = candidate
                    except Exception:
                        pass

            # Attempt 4: Last resort - use domain slug if it's descriptive
            if not new_name or is_junk(new_name):
                clean_slug = company.slug
                for suffix in [".com", "-com", ".net", "-net", ".org", "-org"]:
                    if clean_slug.endswith(suffix):
                        clean_slug = clean_slug[:-len(suffix)]
                        break
                
                slug_parts = clean_slug.split("-")
                if len(slug_parts) >= 2:
                    candidate = " ".join(slug_parts).title()
                    if not is_junk(candidate):
                        new_name = candidate

            # If we found a better name, log it
            if new_name and new_name != original_name and not is_junk(new_name):
                index_path = companies_dir / company.slug / "_index.md"
                proposed_fixes.append({
                    "from": original_name,
                    "to": new_name,
                    "file_path": str(index_path)
                })
                if len(proposed_fixes) <= 10:
                    console.print(f"  [green]Proposed:[/green] {company.slug}: {original_name} -> {new_name}")
                elif len(proposed_fixes) == 11:
                    console.print("  [dim]... more fixes pending ...[/dim]")

    if proposed_fixes:
        with open(output, 'w', encoding='utf-8') as f:
            writer = USVDictWriter(f, fieldnames=["from", "to", "file_path"])
            # No header as per typical cocli USV usage, but writerow is standard
            for fix in proposed_fixes:
                writer.writerow(fix)
        console.print(f"\n[bold green]Success![/bold green] Saved {len(proposed_fixes)} proposed fixes to [cyan]{output}[/cyan]")
    else:
        console.print("\nNo fixes proposed.")

    console.print(f"Stats: Generic/Junk found: {generic_count}, Total scanned: {total_count}")

if __name__ == "__main__":
    app()
