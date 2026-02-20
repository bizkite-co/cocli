import uuid
from rich.console import Console
from pathlib import Path
from typing import Any, Optional
import tty
import termios
import sys
import logging

import shutil
import subprocess

from ..models.companies.company import Company
from ..models.people.person import Person  # Import Company and Person models
from .paths import paths
from .text_utils import slugify

logger = logging.getLogger(__name__)

UNIT_SEP = "\x1f" # ASCII Unit Separator

def get_place_id_shard(place_id: str) -> str:
    """
    Returns a deterministic shard for a Place ID.
    Uses the 6th character (index 5) for 1-level sharding.
    """
    if not place_id or len(place_id) < 6:
        return "_"
    return place_id[5]

def get_geo_shard(lat: float, lon: float) -> str:
    """
    Returns a geographic shard string for a coordinate pair.
    Rounds to 1 decimal place (tenth-degree grid).
    Format: 'lat_{lat}/lon_{lon}'
    """
    l1 = round(float(lat), 1)
    o1 = round(float(lon), 1)
    return f"lat_{l1}/lon_{o1}"

def create_company_files(company: Company, company_dir: Path) -> Path:
    """
    Creates the directory and files for a new company, including its _index.md and tags.lst.
    If the company already exists, it updates the _index.md and tags.lst files, merging data.
    """
    company_dir.mkdir(parents=True, exist_ok=True)
    (company_dir / "contacts").mkdir(exist_ok=True)
    (company_dir / "meetings").mkdir(exist_ok=True)

    # 1. Load existing company if it exists
    existing_company = Company.from_directory(company_dir)
    
    if existing_company:
        # 2. Merge new data into existing one
        existing_company.merge_with(company)
        # 3. Save the merged result
        existing_company.save(base_dir=company_dir.parent)
    else:
        # 2. Just save the new company
        company.save(base_dir=company_dir.parent)

    return company_dir

def create_person_files(person: Person, person_dir: Path) -> Path:
    """
    Creates or updates the markdown file for a person and creates symlinks.
    """
    person_dir.mkdir(parents=True, exist_ok=True)
    person_file = person_dir / f"{slugify(person.name)}.md"

    # Use the model's save method which handles safe_dump and index sync
    person.save(person_file, base_dir=person_dir.parent)

    # --- Create Symlinks ---
    if person.company_name:
        company_slug = slugify(person.company_name)
        company_dir = paths.companies.path / company_slug

        if company_dir.exists():
            # Create Company-to-Person Symlink
            company_contacts_dir = company_dir / "contacts"
            company_contacts_dir.mkdir(exist_ok=True)
            symlink_path_in_company = company_contacts_dir / person_dir.name
            if not symlink_path_in_company.exists():
                symlink_path_in_company.symlink_to(person_dir, target_is_directory=True)

            # Create Person-to-Company Symlink
            person_companies_dir = person_dir / "companies"
            person_companies_dir.mkdir(exist_ok=True)
            symlink_path_in_person = person_companies_dir / company_dir.name
            if not symlink_path_in_person.exists():
                symlink_path_in_person.symlink_to(company_dir, target_is_directory=True)

    return person_file

def _format_entity_for_fzf(entity_type: str, entity: Any) -> str:
    """
    Formats a company or person object into a string for fzf display.
    """
    if entity_type == "company":
        display_name = entity.name
        if entity.average_rating is not None and entity.reviews_count is not None:
            display_name += f" ({entity.average_rating:.1f} ★, {entity.reviews_count} reviews)"
        if entity.visits_per_day is not None:
            display_name += f" ({entity.visits_per_day} visits)"
        return f"COMPANY:{display_name} -- {entity.slug}"
    elif entity_type == "person":
        return f"PERSON:{entity.name}:{entity.company_name if entity.company_name else ''}"
    return ""

def generate_company_hash(data: dict[str, Any]) -> str:
    """Generates a stable hash from company data."""
    # Normalize and combine the fields
    name = data.get("Name", "").lower().strip()
    street = data.get("Street_Address", "").lower().strip()
    city = data.get("City", "").lower().strip()
    state = data.get("State", "").lower().strip()
    zip_code = data.get("Zip", "").lower().strip()

    # Create a consistent string to hash
    hash_string = f"{name}-{street}-{city}-{state}-{zip_code}"

    # Generate the hash
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, hash_string))

def deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively merges 'overrides' into 'base'.
    Nested dictionaries are merged, other values are overwritten.
    """
    for key, value in overrides.items():
        if isinstance(value, dict) and key in base and isinstance(base[key], dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base

def _getch() -> str:
    """
    Reads a single character from stdin without echoing it to the console
    and without requiring the user to press Enter.
    Works for Unix-like systems.
    """
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch

console = Console()

def run_fzf(fzf_input: str) -> Optional[str]:
    fzf_path = shutil.which("fzf")
    if not fzf_path:
        console.print("[bold red]Error:[/bold red] 'fzf' command not found.")
        console.print("Please install fzf to use this feature. (e.g., `brew install fzf` or `sudo apt install fzf`)")
        return None
    try:
        result = subprocess.run(
            [fzf_path],
            input=fzf_input,
            text=True,
            capture_output=True,
            check=False # check=False to handle non-zero exit codes gracefully
        )
        if result.returncode == 0:
            return result.stdout.strip()
        elif result.returncode == 1: # No match
            return None
        elif result.returncode == 130: # Ctrl-C
            return None
        else:
            console.print(f"[bold red]Error during fzf selection:[/bold red] {result.stderr.strip()}")
            return None
    except FileNotFoundError:
        # This is redundant now with shutil.which, but good for safety
        console.print("Error: 'fzf' command not found. Please ensure fzf is installed and in your PATH.")
        return None