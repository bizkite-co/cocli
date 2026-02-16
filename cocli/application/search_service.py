import duckdb
import os
import logging
import time
import threading
import json
from typing import List, Optional, Any, cast, Dict
from cocli.core.cache import get_cached_items, get_cache_path
from cocli.core.config import get_campaign, get_cocli_base_dir
from cocli.core.exclusions import ExclusionManager
from cocli.models.search import SearchResult

logger = logging.getLogger(__name__)

# Module-level cache for DuckDB connection and state
_con: Optional[duckdb.DuckDBPyConnection] = None
_last_cache_mtime: float = -1.0
_last_checkpoint_mtime: float = -1.0
_last_campaign: Optional[str] = None
_lock = threading.RLock()

# Standard schema for GoogleMapsProspect USV
PROSPECT_COLUMNS = {
    "place_id": "VARCHAR",
    "company_slug": "VARCHAR",
    "name": "VARCHAR",
    "phone": "VARCHAR",
    "created_at": "VARCHAR",
    "updated_at": "VARCHAR",
    "version": "INTEGER",
    "processed_by": "VARCHAR",
    "company_hash": "VARCHAR",
    "keyword": "VARCHAR",
    "full_address": "VARCHAR",
    "street_address": "VARCHAR",
    "city": "VARCHAR",
    "zip": "VARCHAR",
    "municipality": "VARCHAR",
    "state": "VARCHAR",
    "country": "VARCHAR",
    "timezone": "VARCHAR",
    "phone_standard_format": "VARCHAR",
    "website": "VARCHAR",
    "domain": "VARCHAR",
    "first_category": "VARCHAR",
    "second_category": "VARCHAR",
    "claimed_google_my_business": "VARCHAR",
    "reviews_count": "INTEGER",
    "average_rating": "DOUBLE",
    "hours": "VARCHAR",
    "saturday": "VARCHAR",
    "sunday": "VARCHAR",
    "monday": "VARCHAR",
    "tuesday": "VARCHAR",
    "wednesday": "VARCHAR",
    "thursday": "VARCHAR",
    "friday": "VARCHAR",
    "latitude": "DOUBLE",
    "longitude": "DOUBLE",
    "coordinates": "VARCHAR",
    "plus_code": "VARCHAR",
    "menu_link": "VARCHAR",
    "gmb_url": "VARCHAR",
    "cid": "VARCHAR",
    "google_knowledge_url": "VARCHAR",
    "kgmid": "VARCHAR",
    "image_url": "VARCHAR",
    "favicon": "VARCHAR",
    "review_url": "VARCHAR",
    "facebook_url": "VARCHAR",
    "linkedin_url": "VARCHAR",
    "instagram_url": "VARCHAR",
    "thumbnail_url": "VARCHAR",
    "reviews": "VARCHAR",
    "quotes": "VARCHAR",
    "uuid": "VARCHAR",
    "discovery_phrase": "VARCHAR",
    "discovery_tile_id": "VARCHAR"
}

def get_fuzzy_search_results(
    search_query: str = "",
    item_type: Optional[str] = None,
    campaign_name: Optional[str] = None,
    force_rebuild_cache: bool = False,
    filters: Optional[Dict[str, Any]] = None,
    sort_by: Optional[str] = None
) -> List[SearchResult]:
    """
    Provides fuzzy search results for companies and people, respecting campaign context.
    Uses DuckDB for efficient querying of both the fz cache and the primary USV checkpoint index.
    """
    global _con, _last_cache_mtime, _last_checkpoint_mtime, _last_campaign
    
    with _lock:
        start_total = time.perf_counter()
        campaign = campaign_name or get_campaign()
        cache_path = get_cache_path(campaign=campaign)
        checkpoint_path = get_cocli_base_dir() / "campaigns" / campaign / "indexes" / "google_maps_prospects" / "prospects.checkpoint.usv" if campaign else None
        
        # 1. Ensure JSON cache exists (for people and tags)
        if not cache_path.exists() or force_rebuild_cache:
            get_cached_items(campaign=campaign, force_rebuild=True)
            if not cache_path.exists():
                return []

        current_cache_mtime = os.path.getmtime(cache_path)
        current_checkpoint_mtime = os.path.getmtime(checkpoint_path) if checkpoint_path and checkpoint_path.exists() else -1.0

        try:
            if _con is None:
                _con = duckdb.connect(database=':memory:')
                _last_cache_mtime = -1.0
                _last_checkpoint_mtime = -1.0

            # 2. Rebuild DuckDB table only if source files changed or campaign switched
            if _last_cache_mtime != current_cache_mtime or \
               _last_checkpoint_mtime != current_checkpoint_mtime or \
               _last_campaign != campaign:
                
                t0 = time.perf_counter()
                _con.execute("DROP TABLE IF EXISTS items_cache")
                _con.execute("DROP TABLE IF EXISTS items_checkpoint")
                _con.execute("DROP VIEW IF EXISTS items")
                
                # A. Load JSON Cache (Source for People and Tags)
                _con.execute(f"""
                    CREATE TABLE items_cache AS 
                    SELECT 
                        COALESCE(CAST(i.type AS VARCHAR), 'unknown') as type,
                        COALESCE(CAST(i.name AS VARCHAR), 'Unknown') as name,
                        CAST(i.slug AS VARCHAR) as slug,
                        CAST(i.domain AS VARCHAR) as domain,
                        CAST(i.email AS VARCHAR) as email,
                        CAST(i.phone_number AS VARCHAR) as phone_number,
                        list_filter(CAST(i.tags AS VARCHAR[]), x -> x IS NOT NULL) as tags,
                        COALESCE(CAST(i.display AS VARCHAR), CAST(i.name AS VARCHAR), 'Unknown') as display,
                        NULL as last_modified,
                        1 as priority
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

                # B. Load USV Checkpoint (Direct Source for fresh Company data)
                if checkpoint_path and checkpoint_path.exists():
                    _con.execute(f"""
                        CREATE TABLE items_checkpoint AS
                        SELECT 
                            'company' as type,
                            name,
                            company_slug as slug,
                            domain,
                            NULL as email,
                            phone as phone_number,
                            list_filter([keyword], x -> x IS NOT NULL) as tags,
                            name as display,
                            updated_at as last_modified,
                            0 as priority
                        FROM read_csv('{checkpoint_path}', 
                                     delim='\x1f', 
                                     header=False, 
                                     quote='',
                                     columns={json.dumps(PROSPECT_COLUMNS)}, 
                                     ignore_errors=True)
                    """)
                else:
                    _con.execute("CREATE TABLE items_checkpoint (type VARCHAR, name VARCHAR, slug VARCHAR, domain VARCHAR, email VARCHAR, phone_number VARCHAR, tags VARCHAR[], display VARCHAR, last_modified VARCHAR, priority INTEGER)")

                # C. Unified View with Deduplication (Favor Checkpoint over Cache)
                _con.execute("""
                    CREATE VIEW items AS 
                    SELECT * FROM (
                        SELECT *, 
                               row_number() OVER (PARTITION BY COALESCE(slug, name), type ORDER BY priority ASC) as row_num
                        FROM (
                            SELECT type, name, slug, domain, email, phone_number, tags, display, last_modified, priority FROM items_checkpoint
                            UNION ALL
                            SELECT type, name, slug, domain, email, phone_number, tags, display, last_modified, priority FROM items_cache
                        )
                    ) WHERE row_num = 1
                """)

                _last_cache_mtime = current_cache_mtime
                _last_checkpoint_mtime = current_checkpoint_mtime
                _last_campaign = campaign
                logger.debug(f"Rebuilt DuckDB search sources in {time.perf_counter() - t0:.4f}s")
            
            # 3. Build Query
            t0 = time.perf_counter()
            sql = "SELECT type, name, slug, domain, email, phone_number, tags, display FROM items WHERE 1=1"
            params: List[Any] = []

            if item_type:
                sql += " AND type = ?"
                params.append(item_type)

            if filters:
                if filters.get("has_contact_info"):
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

            # Ordering
            if sort_by == "recent":
                sql += " ORDER BY last_modified DESC NULLS LAST"
            elif not search_query:
                sql += " ORDER BY name ASC"
            
            sql += " LIMIT 100"

            results = _con.execute(sql, params).fetchall()
            t_query = time.perf_counter() - t0
        except Exception as e:
            logger.error(f"DuckDB search failed: {e}", exc_info=True)
            return []

        # 4. Transform results to Pydantic models
        final_items = []
        for r in results:
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
