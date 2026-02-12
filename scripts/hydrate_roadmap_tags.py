from rich.console import Console
from rich.progress import track
from cocli.core.config import get_cocli_base_dir, get_companies_dir
from cocli.models.company_slug import normalize_company_slug

console = Console()

def hydrate() -> None:
    campaign = "roadmap"
    base_dir = get_cocli_base_dir()
    checkpoint_path = base_dir / "campaigns" / campaign / "indexes" / "google_maps_prospects" / "prospects.checkpoint.usv"
    companies_dir = get_companies_dir()

    if not checkpoint_path.exists():
        console.print(f"[red]Error: Checkpoint not found at {checkpoint_path}[/red]")
        return

    console.print(f"Reading prospects from {checkpoint_path}...")
    
    with open(checkpoint_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    console.print(f"Processing {len(lines)} prospects...")
    
    tagged_count = 0
    missing_dir_count = 0
    
    for line in track(lines, description="Hydrating company tags..."):
        parts = line.split("\x1f")
        if len(parts) < 2:
            continue
            
        slug = normalize_company_slug(parts[1].strip())
        name = parts[2].strip() if len(parts) > 2 else slug
        
        if not slug:
            continue
            
        company_dir = companies_dir / slug
        if not company_dir.exists():
            try:
                company_dir.mkdir(parents=True, exist_ok=True)
                missing_dir_count += 1
            except Exception as e:
                console.print(f"[red]Failed to create directory for {slug}: {e}[/red]")
                continue
            
        # 1. Ensure tags.lst has the campaign tag
        tags_file = company_dir / "tags.lst"
        existing_tags = []
        if tags_file.exists():
            try:
                existing_tags = [t.strip() for t in tags_file.read_text().splitlines() if t.strip()]
            except Exception:
                pass
                
        if campaign not in existing_tags:
            existing_tags.append(campaign)
            unique_tags = sorted(list(set(existing_tags)))
            tags_file.write_text("\n".join(unique_tags) + "\n")
            tagged_count += 1
        else:
            # Already tagged, but we ensure we use the cleaned list for the model below
            unique_tags = sorted(list(set(existing_tags)))

        # 2. Ensure _index.md exists (so it's not skipped by reporting/compilers)
        index_file = company_dir / "_index.md"
        if not index_file.exists():
            from cocli.models.company import Company
            try:
                # Create a minimal company object and save it
                company_obj = Company(
                    name=name or slug,
                    slug=slug,
                    tags=unique_tags
                )
                company_obj.save(email_sync=False) # Skip email sync for speed
            except Exception as e:
                console.print(f"[red]Failed to create _index.md for {slug}: {e}[/red]")

    console.print("\n[bold green]Hydration Complete![/bold green]")
    console.print(f"Ensured '{campaign}' tag in [bold]{tagged_count}[/bold] companies.")
    console.print(f"Created [bold]{missing_dir_count}[/bold] missing company directories.")

if __name__ == "__main__":
    hydrate()
