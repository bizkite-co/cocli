import json
import datetime
import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, cast
import logging

from .config import get_cocli_base_dir, get_companies_dir, get_people_dir
from .utils import _format_entity_for_fzf

logger = logging.getLogger(__name__)

CACHE_FILE_NAME = "fz_cache.json"

def get_cache_path(campaign: Optional[str] = None) -> Path:
    """Returns the path to the fz cache file."""
    if campaign:
        safe_name = campaign.replace("/", "_").replace("\\", "_")
        return get_cocli_base_dir() / f"fz_cache_{safe_name}.json"
    return get_cocli_base_dir() / CACHE_FILE_NAME

def _get_most_recent_mtime(directory: Path) -> Optional[float]:
    """Gets the most recent modification time using fast scanning."""
    if not directory.exists():
        return None
    
    max_mtime = directory.stat().st_mtime
    try:
        with os.scandir(directory) as it:
            for entry in it:
                mtime = entry.stat().st_mtime
                if mtime > max_mtime:
                    max_mtime = mtime
    except Exception:
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

    if companies_mtime is not None and companies_mtime > cache_mtime:
        return False
    if people_mtime is not None and people_mtime > cache_mtime:
        return False

    return True

def read_cache(campaign: Optional[str] = None) -> List[Dict[str, Any]]:
    """Reads the cache file."""
    cache_path = get_cache_path(campaign=campaign)
    if not cache_path.exists():
        return []
    with open(cache_path, 'r') as f:
        try:
            data = json.load(f)
            return cast(List[Dict[str, Any]], data.get("items", []))
        except Exception:
            return []

def write_cache(items: List[Dict[str, Any]], campaign: Optional[str] = None) -> None:
    """Writes items to the cache file."""
    cache_path = get_cache_path(campaign=campaign)
    with open(cache_path, 'w') as f:
        json.dump({"metadata": {"created_at": datetime.datetime.now(datetime.UTC).isoformat()}, "items": items}, f)

def _fast_extract_metadata(index_path: Path) -> Dict[str, Any]:
    """
    Extremely fast regex-based frontmatter extraction to avoid Pydantic overhead.
    """
    data = {}
    try:
        # Just read the first 2KB, usually enough for frontmatter
        with open(index_path, "r", encoding="utf-8") as f:
            content = f.read(2048)
            
        # Match name
        m = re.search(r"^name:\s*(.*)$", content, re.MULTILINE)
        if m: data["name"] = m.group(1).strip().strip('"').strip("'")
        
        # Match domain
        m = re.search(r"^domain:\s*(.*)$", content, re.MULTILINE)
        if m: data["domain"] = m.group(1).strip()
        
        # Match email
        m = re.search(r"^email:\s*(.*)$", content, re.MULTILINE)
        if m: data["email"] = m.group(1).strip()

        # Match place_id
        m = re.search(r"^place_id:\s*(.*)$", content, re.MULTILINE)
        if m: data["place_id"] = m.group(1).strip()

        # Match tags (handles both list and single line)
        tags = []
        # Multi-line list pattern
        if "tags:" in content:
            tags_section = content.split("tags:")[1].split("\n\n")[0]
            for line in tags_section.split("\n"):
                line = line.strip()
                if line.startswith("- "):
                    tags.append(line[2:].strip())
        data["tags"] = tags

    except Exception:
        pass
    return data

def build_cache(campaign: Optional[str] = None) -> List[Dict[str, Any]]:
    """Builds the cache from source files with optimized scanning."""
    logger.info("Building fz cache (regex-optimized)...")
    all_items = []
    companies_dir = get_companies_dir()
    people_dir = get_people_dir()

    if companies_dir.exists():
        with os.scandir(companies_dir) as it:
            for entry in it:
                if entry.is_dir():
                    slug = entry.name
                    index_path = Path(entry.path) / "_index.md"
                    if not index_path.exists():
                        continue
                        
                    meta = _fast_extract_metadata(index_path)
                    name = meta.get("name", slug)
                    tags = meta.get("tags", [])
                    
                    if campaign and campaign not in tags:
                        continue
                    
                    # We store just enough for the fuzzy search list and DuckDB join
                    all_items.append({
                        "type": "company",
                        "name": name,
                        "tags": tags,
                        "email": meta.get("email"),
                        "domain": meta.get("domain"),
                        "slug": slug,
                        "place_id": meta.get("place_id"),
                        "display": f"COMPANY:{name} -- {slug}"
                    })

    if people_dir.exists():
        with os.scandir(people_dir) as it:
            for entry in it:
                if entry.is_file() and entry.name.endswith(".md"):
                    # For people, we still use simple regex or just the name
                    path = Path(entry.path)
                    meta = _fast_extract_metadata(path)
                    name = meta.get("name", path.stem)
                    tags = meta.get("tags", [])
                    
                    if campaign and campaign not in tags:
                        continue
                        
                    all_items.append({
                        "type": "person",
                        "name": name,
                        "tags": tags,
                        "display": f"PERSON:{name}"
                    })
    
    logger.info(f"Cache build complete. Found {len(all_items)} items.")
    write_cache(all_items, campaign=campaign)
    return all_items

def get_cached_items(filter_str: Optional[str] = None, campaign: Optional[str] = None, force_rebuild: bool = False) -> List[Dict[str, Any]]:
    """Gets items from cache. Rebuilds cache ONLY if necessary."""
    if force_rebuild or not is_cache_valid(campaign=campaign):
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
