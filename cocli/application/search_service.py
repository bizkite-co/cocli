import duckdb
import os
import logging
import time
import threading
from typing import List, Optional, Any, cast, Dict
from cocli.core.cache import get_cached_items, get_cache_path
from cocli.core.config import get_campaign
from cocli.core.exclusions import ExclusionManager
from cocli.models.search import SearchResult

logger = logging.getLogger(__name__)

# Module-level cache for DuckDB connection and state
_con: Optional[duckdb.DuckDBPyConnection] = None
_last_cache_mtime: float = -1.0
_last_campaign: Optional[str] = None
_lock = threading.RLock()

def get_fuzzy_search_results(
    search_query: str = "",
    item_type: Optional[str] = None,
    campaign_name: Optional[str] = None,
    force_rebuild_cache: bool = False,
    filters: Optional[Dict[str, Any]] = None
) -> List[SearchResult]:
    """
    Provides fuzzy search results for companies and people, respecting campaign context.
    Uses DuckDB for efficient querying of the fz cache.
    """
    global _con, _last_cache_mtime, _last_campaign
    
    with _lock:
        start_total = time.perf_counter()
        campaign = campaign_name or get_campaign()
        cache_path = get_cache_path(campaign=campaign)
        
        # 1. Check if the JSON cache file itself exists
        if not cache_path.exists() or force_rebuild_cache:
            get_cached_items(campaign=campaign, force_rebuild=True)
            if not cache_path.exists():
                return []

        current_mtime = os.path.getmtime(cache_path)

        try:
            if _con is None:
                _con = duckdb.connect(database=':memory:')
                _last_cache_mtime = -1.0

            # 2. Rebuild DuckDB table only if cache file changed or campaign switched
            if _last_cache_mtime != current_mtime or _last_campaign != campaign:
                t0 = time.perf_counter()
                _con.execute("DROP TABLE IF EXISTS items")
                
                # Explicitly define the columns for the items inside the array.
                # read_json with a defined schema is the most robust and fastest way.
                _con.execute(f"""
                    CREATE TABLE items AS 
                    SELECT 
                        COALESCE(CAST(i.type AS VARCHAR), 'unknown') as type,
                        COALESCE(CAST(i.name AS VARCHAR), 'Unknown') as name,
                        CAST(i.slug AS VARCHAR) as slug,
                        CAST(i.domain AS VARCHAR) as domain,
                        CAST(i.email AS VARCHAR) as email,
                        CAST(i.phone_number AS VARCHAR) as phone_number,
                        CAST(i.tags AS VARCHAR[]) as tags,
                        COALESCE(CAST(i.display AS VARCHAR), CAST(i.name AS VARCHAR), 'Unknown') as display
                    FROM (
                        SELECT unnest(items) as i 
                        FROM read_json('{cache_path}', 
                            columns={{
                                'items': 'STRUCT(
                                    "type" VARCHAR, 
                                    "name" VARCHAR, 
                                    "slug" VARCHAR, 
                                    "domain" VARCHAR, 
                                    "email" VARCHAR, 
                                    "phone_number" VARCHAR, 
                                    "tags" VARCHAR[], 
                                    "display" VARCHAR
                                )[]'
                            }}
                        )
                    )
                """)
                _last_cache_mtime = current_mtime
                _last_campaign = campaign
                logger.debug(f"Rebuilt DuckDB search table from JSON in {time.perf_counter() - t0:.4f}s")
            
            # 3. Build Query
            t0 = time.perf_counter()
            sql = "SELECT type, name, slug, domain, email, phone_number, tags, display FROM items WHERE 1=1"
            params: List[Any] = []

            if item_type:
                sql += " AND type = ?"
                params.append(item_type)

            if filters:
                if filters.get("has_contact_info"):
                    # Keep if (Email is present) OR (Phone is present)
                    # DuckDB JSON extraction can return 'null' string for missing values
                    sql += """ AND (
                        (email IS NOT NULL AND email != '' AND email != 'null') 
                        OR 
                        (phone_number IS NOT NULL AND phone_number != '' AND phone_number != 'null')
                    )"""
                elif filters.get("has_email_and_phone"):
                    sql += " AND email IS NOT NULL AND email != '' AND email != 'null' AND phone_number IS NOT NULL AND phone_number != '' AND phone_number != 'null'"

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

            # Limit results for performance if query is empty
            if not search_query:
                sql += " LIMIT 100"

            results = _con.execute(sql, params).fetchall()
            t_query = time.perf_counter() - t0
        except Exception as e:
            logger.error(f"DuckDB search failed: {e}", exc_info=True)
            return []

        # 4. Transform results to Pydantic models
        final_items = []
        for r in results[:100]:
            final_items.append(SearchResult(
                type=str(r[0]),
                name=str(r[1]),
                slug=str(r[2]) if r[2] else None,
                domain=str(r[3]) if r[3] else None,
                email=str(r[4]) if r[4] else None,
                phone_number=str(r[5]) if r[5] else None,
                tags=cast(List[str], r[6]) if r[6] else [],
                display=str(r[7]),
                unique_id=str(r[2]) if r[2] else str(r[1]) or "unknown"
            ))

        logger.debug(f"Fuzzy search '{search_query}' (type={item_type}) took {time.perf_counter() - start_total:.4f}s (query={t_query:.4f}s)")
        return final_items
