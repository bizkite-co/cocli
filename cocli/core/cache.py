import os
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from .config import get_cocli_base_dir, get_companies_dir, get_people_dir
from ..models.company_cache import CompanyCacheItem

logger = logging.getLogger(__name__)

CACHE_FILE_NAME = "company_cache.usv"

def get_cache_path(campaign: Optional[str] = None) -> Path:
    """Returns the directory where the company cache index is stored."""
    base = get_cocli_base_dir()
    if campaign:
        safe_name = campaign.replace("/", "_").replace("\\", "_")
        return base / "campaigns" / safe_name / "indexes" / "company_cache"
    return base / "indexes" / "company_cache"

def _get_most_recent_mtime(directory: Path) -> Optional[float]:
    """Fast approach to check if any source files changed."""
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
    """Checks if the USV cache is valid compared to source folders."""
    cache_dir = get_cache_path(campaign=campaign)
    cache_file = cache_dir / CACHE_FILE_NAME
    if not cache_file.exists():
        return False

    # 1. Check Schema Version (column count and header presence)
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            first_line = f.readline()
            if first_line:
                from .utils import UNIT_SEP
                # If first line contains 'slug', it's a header - we don't use headers anymore
                if "slug" in first_line:
                    logger.info("Cache contains header. Invalidating.")
                    return False
                
                cols = first_line.split(UNIT_SEP)
                # We expect 8 columns now: slug, name, type, domain, email, phone_number, tags, display
                if len(cols) != 8:
                    logger.info(f"Cache schema mismatch (found {len(cols)} cols, expected 8). Invalidating.")
                    return False
    except Exception:
        return False

    # 2. Check MTime
    cache_mtime = cache_file.stat().st_mtime
    companies_mtime = _get_most_recent_mtime(get_companies_dir())
    people_mtime = _get_most_recent_mtime(get_people_dir())

    if companies_mtime is not None and companies_mtime > cache_mtime:
        return False
    if people_mtime is not None and people_mtime > cache_mtime:
        return False

    return True

def _fast_extract_metadata(index_path: Path) -> Dict[str, Any]:
    """Regex-based frontmatter extraction."""
    data = {}
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            content = f.read(2048)
            
        m = re.search(r"^name:\s*(.*)$", content, re.MULTILINE)
        if m:
            data["name"] = m.group(1).strip().strip('"').strip("'")
        
        m = re.search(r"^domain:\s*(.*)$", content, re.MULTILINE)
        if m:
            data["domain"] = m.group(1).strip()
        
        m = re.search(r"^email:\s*(.*)$", content, re.MULTILINE)
        if m:
            data["email"] = m.group(1).strip()

        m = re.search(r"^phone:\s*(.*)$", content, re.MULTILINE)
        if m:
            data["phone"] = m.group(1).strip()

        tags = []
        if "tags:" in content:
            # Match either [tag1, tag2] or bulleted list
            flow_match = re.search(r"^tags:\s*\[(.*)\]", content, re.MULTILINE)
            if flow_match:
                tags = [t.strip().strip('"').strip("'") for t in flow_match.group(1).split(",")]
            else:
                tags_section = content.split("tags:")[1].split("\n\n")[0]
                for line in tags_section.split("\n"):
                    line = line.strip()
                    if line.startswith("- "):
                        tags.append(line[2:].strip())
        data["tags"] = tags
    except Exception:
        pass
    return data

def build_cache(campaign: Optional[str] = None) -> None:
    """Builds the USV search cache and its datapackage.json."""
    logger.info(f"Building high-performance search cache for {campaign or 'global'}...")
    items: List[CompanyCacheItem] = []
    companies_dir = get_companies_dir()
    people_dir = get_people_dir()

    if companies_dir.exists():
        with os.scandir(companies_dir) as it:
            for entry in it:
                if entry.is_dir():
                    idx_path = Path(entry.path) / "_index.md"
                    if not idx_path.exists():
                        continue
                    
                    meta = _fast_extract_metadata(idx_path)
                    tags = meta.get("tags", [])
                    if campaign and campaign not in tags:
                        continue
                    
                    name = meta.get("name", entry.name)
                    items.append(CompanyCacheItem(
                        slug=entry.name,
                        name=name,
                        type="company",
                        domain=meta.get("domain"),
                        email=meta.get("email"),
                        phone_number=meta.get("phone"),
                        tags=tags,
                        display=f"COMPANY:{name} -- {entry.name}"
                    ))

    if people_dir.exists():
        with os.scandir(people_dir) as it:
            for entry in it:
                if entry.is_file() and entry.name.endswith(".md"):
                    meta = _fast_extract_metadata(Path(entry.path))
                    tags = meta.get("tags", [])
                    if campaign and campaign not in tags:
                        continue
                    
                    name = meta.get("name", Path(entry.name).stem)
                    items.append(CompanyCacheItem(
                        slug=Path(entry.name).stem,
                        name=name,
                        type="person",
                        phone_number=meta.get("phone"),
                        tags=tags,
                        display=f"PERSON:{name}"
                    ))

    cache_dir = get_cache_path(campaign=campaign)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / CACHE_FILE_NAME
    
    # Tiny sleep to ensure mtime > source files in fast tests
    import time
    time.sleep(0.01)

    with open(cache_file, "w", encoding="utf-8") as f:
        for item in items:
            f.write(item.to_usv())
            
    # Save Frictionless schema
    CompanyCacheItem.save_datapackage(cache_dir)
    logger.info(f"Cache build complete. Saved {len(items)} items to {cache_file}")

def get_cached_items(filter_str: Optional[str] = None, campaign: Optional[str] = None, force_rebuild: bool = False) -> List[Dict[str, Any]]:
    """LEGACY ADAPTER: Still used by some CLI commands. Rebuilds USV if needed."""
    if force_rebuild or not is_cache_valid(campaign=campaign):
        build_cache(campaign=campaign)
    
    # Simple JSON-like list for legacy compatibility
    # In the future, we'll remove this entirely in favor of DuckDB queries.
    return []
