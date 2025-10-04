import os
import json
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from .config import get_cocli_base_dir, get_companies_dir, get_people_dir
from ..models.company import Company
from ..models.person import Person
from .utils import _format_entity_for_fzf

CACHE_FILE_NAME = "fz_cache.json"

def get_cache_path() -> Path:
    """Returns the path to the fz cache file."""
    return get_cocli_base_dir() / CACHE_FILE_NAME

def _get_most_recent_mtime(directory: Path) -> Optional[float]:
    """Recursively gets the most recent modification time of files in a directory."""
    max_mtime = None
    if not directory.exists():
        return None
    for root, _, files in os.walk(directory):
        for file in files:
            try:
                mtime = (Path(root) / file).stat().st_mtime
                if max_mtime is None or mtime > max_mtime:
                    max_mtime = mtime
            except FileNotFoundError:
                # This can happen if we encounter a broken symlink.
                # We can safely ignore it for the purpose of checking modification times.
                pass
    return max_mtime

def is_cache_valid() -> bool:
    """Checks if the cache is valid by comparing modification times."""
    cache_path = get_cache_path()
    if not cache_path.exists():
        return False

    cache_mtime = cache_path.stat().st_mtime

    companies_dir = get_companies_dir()
    people_dir = get_people_dir()

    companies_mtime = _get_most_recent_mtime(companies_dir)
    people_mtime = _get_most_recent_mtime(people_dir)

    if companies_mtime and companies_mtime > cache_mtime:
        return False
    if people_mtime and people_mtime > cache_mtime:
        return False

    return True

def read_cache() -> List[Dict[str, Any]]:
    """Reads the cache file and returns its items."""
    cache_path = get_cache_path()
    if not cache_path.exists():
        return []
    with open(cache_path, 'r') as f:
        try:
            data = json.load(f)
            return data.get("items", [])
        except json.JSONDecodeError:
            return []

def write_cache(items: List[Dict[str, Any]]):
    """Writes items to the cache file."""
    cache_path = get_cache_path()
    with open(cache_path, 'w') as f:
        json.dump({"metadata": {"created_at": datetime.datetime.utcnow().isoformat()}, "items": items}, f)

def build_cache() -> List[Dict[str, Any]]:
    """Builds the cache from source files."""
    all_items = []
    companies_dir = get_companies_dir()
    people_dir = get_people_dir()

    if companies_dir.exists():
        for company_dir in companies_dir.iterdir():
            if company_dir.is_dir():
                company = Company.from_directory(company_dir)
                if company:
                    all_items.append({
                        "type": "company",
                        "name": company.name,
                        "tags": company.tags,
                        "display": _format_entity_for_fzf("company", company)
                    })

    if people_dir.exists():
        for person_file in people_dir.iterdir():
            if person_file.is_file() and person_file.suffix == ".md":
                person = Person.from_file(person_file)
                if person:
                    all_items.append({
                        "type": "person",
                        "name": person.name,
                        "company_name": person.company_name,
                        "tags": person.tags,
                        "display": _format_entity_for_fzf("person", person)
                    })
    
    write_cache(all_items)
    return all_items

def get_cached_items(tag_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Gets items from cache. Rebuilds cache if invalid.
    Filters by tag if a filter is provided.
    """
    if not is_cache_valid():
        items = build_cache()
    else:
        items = read_cache()

    if tag_filter:
        items = [item for item in items if tag_filter in item.get("tags", [])]

    return items
