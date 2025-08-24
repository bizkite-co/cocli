import re
from pathlib import Path
from typing import Any, List, Optional
import tty
import termios
import sys

import yaml # This import might not be needed here if models handle YAML loading

from .models import Company, Person # Import Company and Person models
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

    existing_company = None
    if index_path.exists():
        existing_company = Company.from_directory(company_dir)

    if existing_company:
        # Merge new company data into existing company
        updated_company_data = existing_company.model_dump() # Get existing data as dict (field names)
        new_company_data = company.model_dump() # Get new data as dict (field names)

        # Merge simple fields (new data takes precedence)
        for key, value in new_company_data.items():
            if key not in ["tags", "categories"] and value is not None:
                updated_company_data[key] = value

        # Merge tags (unique values)
        existing_tags = set(updated_company_data.get("tags", []))
        new_tags = set(new_company_data.get("tags", []))
        updated_company_data["tags"] = sorted(list(existing_tags.union(new_tags)))

        # Merge categories (unique values)
        existing_categories = set(updated_company_data.get("categories", []))
        new_categories = set(new_company_data.get("categories", []))
        updated_company_data["categories"] = sorted(list(existing_categories.union(new_categories)))

        # Recreate Company object from merged data
        company_to_write = Company(**updated_company_data)
    else:
        company_to_write = company

    # Prepare data for YAML front matter (using Pydantic field names)
    company_data_for_yaml = company_to_write.model_dump(exclude={"tags", "categories"}) # Removed by_alias=True

    # Generate YAML front matter
    frontmatter = yaml.dump(company_data_for_yaml, sort_keys=False, default_flow_style=False, allow_unicode=True)

    # Construct _index.md content
    # Preserve existing markdown content if any
    markdown_content = f"\n# {company_to_write.name}\n"
    if index_path.exists():
        content = index_path.read_text()
        if content.startswith("---") and "---" in content[3:]:
            _, md_content_part = content.split("---", 2)[1:]
            markdown_content = md_content_part # Preserve existing markdown content

    index_content = f"---\n{frontmatter}---\n{markdown_content}"
    index_path.write_text(index_content)

    # Write merged tags to tags.lst
    if company_to_write.tags:
        tags_path.write_text("\n".join(company_to_write.tags) + "\n")
    elif tags_path.exists():
        tags_path.unlink() # Remove tags.lst if no tags

    return company_dir

def create_person_files(person_name: str, person_dir: Path, company_name: str) -> Path:
    """
    Creates the markdown file for a new person.
    """
    person_dir.mkdir(parents=True, exist_ok=True)
    person_file = person_dir / f"{slugify(person_name)}.md"
    if not person_file.exists():
        content = f"# {person_name}\n\n- **Company:** {company_name}\n"
        person_file.write_text(content)
    return person_file

def _format_entity_for_fzf(entity_type: str, entity: Any) -> str:
    """
    Formats a company or person object into a string for fzf display.
    """
    if entity_type == "company":
        return f"COMPANY:{entity.name}"
    elif entity_type == "person":
        return f"PERSON:{entity.name}:{entity.company_name if entity.company_name else ''}"
    return ""

def _get_all_searchable_items() -> List[tuple[str, Any]]:
    """
    Gathers all companies and people for fuzzy searching.
    Returns a list of tuples: [("company", Company_obj), ("person", Person_obj)].
    """
    all_items = []
    companies_dir = get_companies_dir()
    people_dir = get_people_dir()

    if companies_dir.exists():
        for company_dir in companies_dir.iterdir():
            if company_dir.is_dir():
                company = Company.from_directory(company_dir)
                if company:
                    all_items.append(("company", company))

    if people_dir.exists():
        for person_file in people_dir.iterdir():
            if person_file.is_file() and person_file.suffix == ".md":
                person = Person.from_directory(person_file)
                if person:
                    all_items.append(("person", person))
    return all_items

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