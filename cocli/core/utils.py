import re
from pathlib import Path
from typing import Any, List, Optional
import tty
import termios
import sys

import yaml # This import might not be needed here if models handle YAML loading

from ..models.company import Company
from ..models.person import Person # Import Company and Person models
from .config import get_companies_dir, get_people_dir # Import directory getters

# Custom representer for None to ensure it's explicitly written as 'null'
def represent_none(self, data):
    return self.represent_scalar('tag:yaml.org,2002:null', 'null')

yaml.add_representer(type(None), represent_none)

def slugify(text: str) -> str:
    """Converts text to a filesystem-friendly slug."""
    text = text.lower()
    text = re.sub(r'[\s\W]+', '-', text)
    return text.strip('-')

def create_company_files(company: Company, company_dir: Path) -> Path:
    """
    Creates the directory and files for a new company, including its _index.md and tags.lst.
    If the company already exists, it updates the _index.md and tags.lst files, merging data.
    """
    company_dir.mkdir(parents=True, exist_ok=True)
    (company_dir / "contacts").mkdir(exist_ok=True)
    (company_dir / "meetings").mkdir(exist_ok=True)

    index_path = company_dir / "_index.md"
    tags_path = company_dir / "tags.lst"

    existing_frontmatter_data = {}
    markdown_content = f"\n# {company.name}\n" # Default markdown content

    existing_tags = set()
    if tags_path.exists():
        existing_tags.update(tags_path.read_text().strip().splitlines())

    if index_path.exists():
        content = index_path.read_text()
        if content.startswith("---") and "---" in content[3:]:
            frontmatter_str, md_content_part = content.split("---", 2)[1:]
            try:
                existing_frontmatter_data = yaml.safe_load(frontmatter_str) or {}
                markdown_content = md_content_part # Preserve existing markdown content
            except yaml.YAMLError:
                print(f"Warning: Could not parse YAML front matter in {index_path}. Overwriting with new data.")
        else:
            print(f"Warning: No valid YAML front matter found in {index_path}. Overwriting with new data.")

    # Prepare new data for YAML front matter (using Pydantic field names)
    new_company_data_for_yaml = company.model_dump(exclude={"tags", "categories"})
    # Ensure 'name' is not duplicated if it was already in the model_dump
    new_company_data_for_yaml.pop("name", None)

    # Merge existing data with new data (new data takes precedence only if not None/empty)
    merged_data = existing_frontmatter_data.copy()
    for key, new_value in new_company_data_for_yaml.items():
        if new_value is not None and new_value != '':
            merged_data[key] = new_value
        # If new_value is None/empty, and key exists in merged_data, preserve existing value.
        # If new_value is None/empty, and key does not exist in merged_data, add it as None/empty.
        elif key not in merged_data:
            merged_data[key] = new_value

    merged_data["name"] = company.name # Ensure name is always from the new company object

    # Merge tags
    merged_tags = sorted(list(existing_tags.union(set(company.tags))))

    # Merge categories
    existing_categories = set(existing_frontmatter_data.get("categories", []))
    new_categories = set(company.categories)
    merged_categories = sorted(list(existing_categories.union(new_categories)))
    if merged_categories:
        merged_data["categories"] = merged_categories
    elif "categories" in merged_data:
        del merged_data["categories"] # Remove if empty

    # Generate YAML front matter
    frontmatter = yaml.dump(merged_data, sort_keys=False, default_flow_style=False, allow_unicode=True)

    # Construct _index.md content
    index_content = f"---\n{frontmatter}---\n{markdown_content}"

    index_path.write_text(index_content)

    # Write merged tags to tags.lst
    if merged_tags:
        tags_path.write_text("\n".join(merged_tags) + "\n")
    elif tags_path.exists():
        tags_path.unlink() # Remove tags.lst if no tags

    return company_dir

def create_person_files(person: Person, person_dir: Path) -> Path:
    """
    Creates or updates the markdown file for a person, merging tags, and creates symlinks.
    """
    person_dir.mkdir(parents=True, exist_ok=True)
    # Correctly slugify the name for the filename
    person_file = person_dir / f"{slugify(person.name)}.md"

    existing_frontmatter_data = {}
    markdown_content = f"\n# {person.name}\n"  # Default markdown content

    if person_file.exists():
        content = person_file.read_text()
        if content.startswith("---") and "---" in content[3:]:
            frontmatter_str, md_content_part = content.split("---", 2)[1:]
            try:
                existing_frontmatter_data = yaml.safe_load(frontmatter_str) or {}
                markdown_content = md_content_part  # Preserve existing markdown content
            except yaml.YAMLError:
                print(f"Warning: Could not parse YAML front matter in {person_file}. Overwriting with new data.")
        else:
            print(f"Warning: No valid YAML front matter found in {person_file}. Overwriting with new data.")

    # Prepare new data for YAML front matter
    new_person_data_for_yaml = person.model_dump(exclude={'tags'})
    new_person_data_for_yaml.pop("name", None)

    # Merge existing data with new data
    merged_data = existing_frontmatter_data.copy()
    for key, new_value in new_person_data_for_yaml.items():
        if new_value is not None and new_value != '':
            merged_data[key] = new_value
        elif key not in merged_data:
            merged_data[key] = new_value

    merged_data["name"] = person.name

    # Merge tags
    existing_tags = set(existing_frontmatter_data.get('tags', []))
    merged_tags = sorted(list(existing_tags.union(set(person.tags))))
    if merged_tags:
        merged_data['tags'] = merged_tags

    # Generate YAML front matter
    frontmatter = yaml.dump(merged_data, sort_keys=False, default_flow_style=False, allow_unicode=True)

    # Construct file content
    index_content = f"---\n{frontmatter}---\n{markdown_content}"

    person_file.write_text(index_content)

    # --- Create Symlinks ---
    if person.company_name:
        company_slug = slugify(person.company_name)
        company_dir = get_companies_dir() / company_slug

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
        return f"COMPANY:{display_name}"
    elif entity_type == "person":
        return f"PERSON:{entity.name}:{entity.company_name if entity.company_name else ''}"
    return ""



def _getch():
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