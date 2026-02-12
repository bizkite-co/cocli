import duckdb
import os
import logging
from typing import List, Optional, Any
from cocli.core.cache import get_cached_items, get_cache_path
from cocli.core.config import get_campaign
from cocli.core.exclusions import ExclusionManager
from cocli.models.search import SearchResult

logger = logging.getLogger(__name__)

# Module-level cache for DuckDB connection and state
_con: Optional[duckdb.DuckDBPyConnection] = None
_last_cache_mtime: float = -1.0
_last_campaign: Optional[str] = None

def get_fuzzy_search_results(
    search_query: str = "",
    item_type: Optional[str] = None,
    campaign_name: Optional[str] = None,
    force_rebuild_cache: bool = False
) -> List[SearchResult]:
    """
    Provides fuzzy search results for companies and people, respecting campaign context.
    Uses DuckDB for efficient querying of the fz cache.
    """
    global _con, _last_cache_mtime, _last_campaign
    
    import time
    start_total = time.perf_counter()
    
    campaign = campaign_name or get_campaign()
    
    # Check if cache needs rebuild (this also handles file mtime check)
    t0 = time.perf_counter()
    items = get_cached_items(
        filter_str=None,
        campaign=campaign,
        force_rebuild=force_rebuild_cache
    )
    t_cache = time.perf_counter() - t0

    if not items:
        return []

    # Detect if we need to rebuild the DuckDB table based on cache file mtime or campaign change
    cache_path = get_cache_path(campaign=campaign)
    current_mtime = os.path.getmtime(cache_path) if cache_path.exists() else 0.0

    try:
        if _con is None:
            _con = duckdb.connect(database=':memory:')
            _last_cache_mtime = -1.0

        if _last_cache_mtime != current_mtime or _last_campaign != campaign:
            t0 = time.perf_counter()
            # Rebuild the table
            _con.execute("DROP TABLE IF EXISTS items")
            _con.execute("""
                CREATE TABLE items (
                    type VARCHAR,
                    name VARCHAR,
                    slug VARCHAR,
                    domain VARCHAR,
                    email VARCHAR,
                    tags VARCHAR[],
                    display VARCHAR
                )
            """)
            
            rows = []
            for item in items:
                tags = item.get('tags', [])
                if not isinstance(tags, list):
                    tags = []
                else:
                    tags = [str(t) for t in tags if t]
                
                rows.append((
                    item.get('type'),
                    item.get('name'),
                    item.get('slug'),
                    item.get('domain'),
                    item.get('email'),
                    tags,
                    item.get('display')
                ))
                
            _con.executemany("INSERT INTO items VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
            _last_cache_mtime = current_mtime
            _last_campaign = campaign
            logger.debug(f"Rebuilt DuckDB search table in {time.perf_counter() - t0:.4f}s")
        
        # Base query
        t0 = time.perf_counter()
        sql = "SELECT * FROM items WHERE 1=1"
        params: List[Any] = []

        if item_type:
            sql += " AND type = ?"
            params.append(item_type)

        if campaign:
            exclusion_manager = ExclusionManager(campaign=campaign)
            exclusions = exclusion_manager.list_exclusions()
            excluded_domains = [str(exc.domain) for exc in exclusions if exc.domain]
            excluded_slugs = [str(exc.company_slug) for exc in exclusions if exc.company_slug]
            
            if excluded_domains:
                placeholders = ", ".join(["?" for _ in excluded_domains])
                sql += f" AND (domain IS NULL OR domain NOT IN ({placeholders}))"
                params.extend(excluded_domains)
            if excluded_slugs:
                placeholders = ", ".join(["?" for _ in excluded_slugs])
                sql += f" AND (slug IS NULL OR slug NOT IN ({placeholders}))"
                params.extend(excluded_slugs)

        if search_query:
            query_pattern = f"%{search_query.lower()}%"
            sql += """ AND (
                lower(name) LIKE ?
                OR lower(slug) LIKE ?
                OR lower(domain) LIKE ?
                OR lower(email) LIKE ?
                OR lower(display) LIKE ?
                OR array_to_string(tags, ',') LIKE ?
            )"""
            params.extend([query_pattern] * 6)

        results = _con.execute(sql, params).fetchall()
        t_query = time.perf_counter() - t0
    except Exception as e:
        logger.error(f"DuckDB search failed: {e}")
        return []

    seen_ids = set()
    final_items = []
    for r in results:
        tags_list = r[5] if r[5] is not None else []
        item_dict = {
            "type": r[0], "name": r[1], "slug": r[2], "domain": r[3],
            "email": r[4], "tags": tags_list, "display": r[6]
        }
        
        unique_id = item_dict.get("slug") or "unknown"
        original_slug = unique_id
        counter = 1
        while unique_id in seen_ids:
            unique_id = f"{original_slug}-{counter}"
            counter += 1
        seen_ids.add(unique_id)
        item_dict["unique_id"] = unique_id
        final_items.append(SearchResult(**item_dict))

    logger.debug(f"Fuzzy search '{search_query}' (type={item_type}) took {time.perf_counter() - start_total:.4f}s (cache={t_cache:.4f}s, query={t_query:.4f}s)")
    return final_items
