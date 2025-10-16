import os
import json
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging

from .config import get_cocli_base_dir, get_companies_dir, get_people_dir
from ..models.company import Company
from ..models.person import Person
from .utils import _format_entity_for_fzf

CACHE_FILE_NAME = "fz_cache.json"

def get_cache_path(campaign: Optional[str] = None) -> Path:
    """Returns the path to the fz cache file."""
    if campaign:
        return get_cocli_base_dir() / f"fz_cache_{campaign}.json"
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

def is_cache_valid(campaign: Optional[str] = None) -> bool:
    """Checks if the cache is valid by comparing modification times."""
    cache_path = get_cache_path(campaign=campaign)
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

def read_cache(campaign: Optional[str] = None) -> List[Dict[str, Any]]:
    """Reads the cache file and returns its items."""
    cache_path = get_cache_path(campaign=campaign)
    if not cache_path.exists():
        return []
    with open(cache_path, 'r') as f:
        try:
            data = json.load(f)
            return data.get("items", [])
        except json.JSONDecodeError:
            return []

def write_cache(items: List[Dict[str, Any]], campaign: Optional[str] = None):
    """Writes items to the cache file."""
    cache_path = get_cache_path(campaign=campaign)
    with open(cache_path, 'w') as f:
        json.dump({"metadata": {"created_at": datetime.datetime.now(datetime.UTC).isoformat()}, "items": items}, f)

def build_cache(campaign: Optional[str] = None) -> List[Dict[str, Any]]:
    """Builds the cache from source files."""
    logger = logging.getLogger(__name__)
    logger.info("Building fz cache...")
    all_items = []
    companies_dir = get_companies_dir()
    people_dir = get_people_dir()

    logger.debug(f"Searching for companies in: {companies_dir}")
    if companies_dir.exists():
        for company_dir in companies_dir.iterdir():
            logger.debug(f"Processing company directory: {company_dir}")
            if company_dir.is_dir():
                company = Company.from_directory(company_dir)
                if company:
                    if campaign and campaign not in company.tags:
                        continue
                    logger.debug(f"Successfully loaded company: {company.name}")
                    all_items.append({
                        "type": "company",
                        "name": company.name,
                        "tags": company.tags,
                        "email": company.email,
                        "domain": company.domain,
                        "display": _format_entity_for_fzf("company", company)
                    })
                else:
                    logger.warning(f"Failed to load company from directory: {company_dir}")

    logger.debug(f"Searching for people in: {people_dir}")
    if people_dir.exists():
        for person_file in people_dir.iterdir():
            if person_file.is_file() and person_file.suffix == ".md":
                person = Person.from_file(person_file)
                if person:
                    if campaign and campaign not in person.tags:
                        continue
                    all_items.append({
                        "type": "person",
                        "name": person.name,
                        "company_name": person.company_name,
                        "tags": person.tags,
                        "display": _format_entity_for_fzf("person", person)
                    })
    
    logger.info(f"Cache build complete. Found {len(all_items)} items.")
    write_cache(all_items, campaign=campaign)
    return all_items

def get_cached_items(filter_str: Optional[str] = None, campaign: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Gets items from cache. Rebuilds cache if invalid.
    Filters by tag or other conditions if a filter is provided.
    """
    if not is_cache_valid(campaign=campaign):
        items = build_cache(campaign=campaign)
    else:
        items = read_cache(campaign=campaign)

    if filter_str:
        if filter_str.startswith("tag:"):
            tag = filter_str.split(":", 1)[1]
            items = [item for item in items if tag in item.get("tags", [])]
        elif filter_str == "missing:email":
            items = [item for item in items if item.get("type") == "company" and not item.get("email")]

    return items
