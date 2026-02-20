import duckdb
import os
import logging
import time
import threading
from typing import List, Optional, Any, cast, Dict
from cocli.core.cache import get_cache_path, is_cache_valid, build_cache, CACHE_FILE_NAME
from cocli.core.config import get_campaign
from cocli.core.exclusions import ExclusionManager
from cocli.models.search import SearchResult
from cocli.utils.duckdb_utils import load_usv_to_duckdb

logger = logging.getLogger(__name__)

# Module-level cache for DuckDB connection and state
_con: Optional[duckdb.DuckDBPyConnection] = None
_last_cache_mtime: float = -1.0
_last_checkpoint_mtime: float = -1.0
_last_lifecycle_mtime: float = -1.0
_last_campaign: Optional[str] = None
_lock = threading.RLock()

# Cache for template counts: { campaign_name: (timestamp, counts_dict) }
_counts_cache: Dict[str, tuple[float, Dict[str, int]]] = {}
_COUNTS_CACHE_TTL = 300 # 5 minutes

def get_template_counts(campaign_name: Optional[str] = None) -> Dict[str, int]:
    """Returns a dictionary of counts for each template filter."""
    global _con, _counts_cache
    
    campaign = campaign_name or get_campaign()
    if not campaign:
        return {}
        
    now = time.time()
    if campaign in _counts_cache:
        ts, counts = _counts_cache[campaign]
        if now - ts < _COUNTS_CACHE_TTL:
            return counts

    # Non-blocking search trigger
    get_fuzzy_search_results("", item_type="company", campaign_name=campaign, limit=1)

    counts = {}
    with _lock:
        if _con:
            try:
                # Check if the items view actually exists before counting
                check = _con.execute("SELECT 1 FROM information_schema.views WHERE table_name = 'items'").fetchone()
                if not check:
                    return {}

                def get_count(query: str) -> int:
                    res = _con.execute(query).fetchone()
                    return int(res[0]) if res else 0

                # All Leads
                counts["tpl_all"] = get_count("SELECT count(*) FROM items WHERE type = 'company'")
                
                # With Email
                counts["tpl_with_email"] = get_count("SELECT count(*) FROM items WHERE type = 'company' AND email IS NOT NULL AND email != '' AND email != 'null'")
                
                # Missing Email
                counts["tpl_no_email"] = get_count("SELECT count(*) FROM items WHERE type = 'company' AND (email IS NULL OR email = '' OR email = 'null')")
                
                # Actionable
                counts["tpl_actionable"] = get_count("SELECT count(*) FROM items WHERE type = 'company' AND ((email IS NOT NULL AND email != '' AND email != 'null') OR (phone_number IS NOT NULL AND phone_number != '' AND phone_number != 'null'))")
                
                # Missing Address
                counts["tpl_no_address"] = get_count("SELECT count(*) FROM items WHERE type = 'company' AND (street_address IS NULL OR street_address = '' OR street_address = 'null')")
                
                # Top Rated (Rating > 4)
                counts["tpl_top_rated"] = get_count("SELECT count(*) FROM items WHERE type = 'company' AND average_rating >= 4.0")
                
                # Most Reviewed (Reviews > 10)
                counts["tpl_most_reviewed"] = get_count("SELECT count(*) FROM items WHERE type = 'company' AND reviews_count >= 10")
                
            except Exception as e:
                logger.error(f"Failed to get template counts: {e}")
                return {}

    _counts_cache[campaign] = (now, counts)
    return counts

def get_fuzzy_search_results(
    search_query: str = "",
    item_type: Optional[str] = None,
    campaign_name: Optional[str] = None,
    force_rebuild_cache: bool = False,
    filters: Optional[Dict[str, Any]] = None,
    sort_by: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> List[SearchResult]:
    """
    Provides fuzzy search results joined across three high-performance USV indices.
    """
    global _con, _last_cache_mtime, _last_checkpoint_mtime, _last_lifecycle_mtime, _last_campaign
    
    from cocli.core.paths import paths

    campaign = campaign_name or get_campaign()
    # If campaign is 'None' (literal string), treat as None
    if campaign == "None":
        campaign = None

    cache_dir = get_cache_path(campaign=campaign)
    cache_file = cache_dir / CACHE_FILE_NAME
    
    checkpoint_path = None
    lifecycle_dir = None
    lifecycle_path = None
    prospect_dp = None
    if campaign:
        campaign_node = paths.campaign(campaign)
        prospect_idx = campaign_node.index("google_maps_prospects")
        checkpoint_path = prospect_idx.checkpoint
        prospect_dp = prospect_idx.path / "datapackage.json"
        lifecycle_dir = campaign_node.path / "indexes" / "lifecycle"
        lifecycle_path = campaign_node.lifecycle
    else:
        # Check if we should fallback to global search if no campaign
        pass
    
    # 1. NON-BLOCKING CACHE REBUILD
    if force_rebuild_cache or not is_cache_valid(campaign=campaign):
        if not cache_file.exists():
            build_cache(campaign=campaign)
        else:
            if not hasattr(get_fuzzy_search_results, "_building"):
                get_fuzzy_search_results._building = set() # type: ignore
            
            if campaign not in get_fuzzy_search_results._building: # type: ignore
                get_fuzzy_search_results._building.add(campaign) # type: ignore
                def bg_rebuild() -> None:
                    try:
                        build_cache(campaign=campaign)
                    except Exception as e:
                        logger.error(f"Background cache rebuild failed: {e}")
                    finally:
                        get_fuzzy_search_results._building.remove(campaign) # type: ignore
                
                threading.Thread(target=bg_rebuild, daemon=True).start()

    with _lock:
        start_total = time.perf_counter()
        current_cache_mtime = os.path.getmtime(cache_file) if cache_file.exists() else -1.0
        current_checkpoint_mtime = os.path.getmtime(checkpoint_path) if checkpoint_path and checkpoint_path.exists() else -1.0
        current_lifecycle_mtime = os.path.getmtime(lifecycle_path) if lifecycle_path and lifecycle_path.exists() else -1.0

        # Check column existence for dynamic view creation and query building
        def has_col(table: str, col: str) -> bool:
            if not _con:
                return False
            res = _con.execute(f"SELECT count(*) FROM information_schema.columns WHERE table_name = '{table}' AND lower(column_name) = '{col.lower()}'").fetchone()
            return bool(res and res[0] > 0)

        try:
            if _con is None:
                _con = duckdb.connect(database=':memory:')
                _last_cache_mtime = -1.0
                _last_checkpoint_mtime = -1.0
                _last_lifecycle_mtime = -1.0

            if _last_cache_mtime != current_cache_mtime or \
               _last_checkpoint_mtime != current_checkpoint_mtime or \
               _last_campaign != campaign or \
               _last_lifecycle_mtime != current_lifecycle_mtime:
                
                t0 = time.perf_counter()
                _con.execute("DROP VIEW IF EXISTS items")
                _con.execute("DROP TABLE IF EXISTS items_cache")
                _con.execute("DROP TABLE IF EXISTS items_checkpoint")
                _con.execute("DROP TABLE IF EXISTS items_lifecycle")
                
                # A. Load Company Cache USV
                load_usv_to_duckdb(_con, "items_cache", cache_file, cache_dir / "datapackage.json" if cache_dir else None)

                # B. Load Prospect Checkpoint USV
                if checkpoint_path and checkpoint_path.exists():
                    load_usv_to_duckdb(_con, "items_checkpoint", checkpoint_path, prospect_dp)
                else:
                    _con.execute("CREATE TABLE items_checkpoint (place_id VARCHAR, slug VARCHAR, company_slug VARCHAR, name VARCHAR, phone VARCHAR, phone_number VARCHAR, email VARCHAR, tags VARCHAR, created_at VARCHAR, updated_at VARCHAR, version INTEGER, processed_by VARCHAR, company_hash VARCHAR, keyword VARCHAR, full_address VARCHAR, street_address VARCHAR, city VARCHAR, zip VARCHAR, municipality VARCHAR, state VARCHAR, country VARCHAR, timezone VARCHAR, phone_standard_format VARCHAR, website VARCHAR, domain VARCHAR, first_category VARCHAR, second_category VARCHAR, claimed_google_my_business VARCHAR, reviews_count INTEGER, average_rating DOUBLE, hours VARCHAR, saturday VARCHAR, sunday VARCHAR, monday VARCHAR, tuesday VARCHAR, wednesday VARCHAR, thursday VARCHAR, friday VARCHAR, latitude DOUBLE, longitude DOUBLE, coordinates VARCHAR, plus_code VARCHAR, menu_link VARCHAR, gmb_url VARCHAR, cid VARCHAR, google_knowledge_url VARCHAR, kgmid VARCHAR, image_url VARCHAR, favicon VARCHAR, review_url VARCHAR, facebook_url VARCHAR, linkedin_url VARCHAR, instagram_url VARCHAR, thumbnail_url VARCHAR, reviews VARCHAR, quotes VARCHAR, uuid VARCHAR, discovery_phrase VARCHAR, discovery_tile_id VARCHAR)")

                # C. Load Lifecycle Index USV
                if lifecycle_path and lifecycle_path.exists():
                    load_usv_to_duckdb(_con, "items_lifecycle", lifecycle_path, lifecycle_dir / "datapackage.json" if lifecycle_dir else None)
                else:
                    _con.execute("CREATE TABLE items_lifecycle (place_id VARCHAR, scraped_at VARCHAR, details_at VARCHAR, enqueued_at VARCHAR, enriched_at VARCHAR)")

                # D. Unified View - JOIN FIX
                # Standardized utility now maps both tables to use 'slug', 'phone_number', and 'tags'.
                
                t1_slug = "t1.slug" if has_col("items_checkpoint", "slug") else "t1.company_slug" if has_col("items_checkpoint", "company_slug") else "CAST(NULL AS VARCHAR)"
                t1_phone = "t1.phone_number" if has_col("items_checkpoint", "phone_number") else "t1.phone" if has_col("items_checkpoint", "phone") else "CAST(NULL AS VARCHAR)"
                t1_tags = "string_to_array(t1.tags, ';')" if has_col("items_checkpoint", "tags") else "string_to_array(t1.keyword, ';')" if has_col("items_checkpoint", "keyword") else "CAST([] AS VARCHAR[])"
                t2_tags = "string_to_array(t2.tags, ';')" if has_col("items_cache", "tags") else "CAST([] AS VARCHAR[])"

                _con.execute("CREATE VIEW items AS SELECT " +
                    f"COALESCE({t1_slug}, t2.slug) as slug, " +
                    "COALESCE(t1.name, t2.name) as name, " +
                    "COALESCE(t2.type, CAST('company' AS VARCHAR)) as type, " +
                    "COALESCE(t1.domain, t2.domain) as domain, " +
                    "t2.email as email, " +
                    f"COALESCE({t1_phone}, t2.phone_number) as phone_number, " +
                    f"COALESCE({t1_tags}, {t2_tags}) as tags, " +
                    f"COALESCE(t2.display, 'COMPANY:' || COALESCE(t1.name, t2.name) || ' -- ' || COALESCE({t1_slug}, t2.slug)) as display, " +
                    "COALESCE(t1.updated_at, CAST(NULL AS VARCHAR)) as last_modified, " +
                    "COALESCE(t1.average_rating, CAST(NULL AS DOUBLE)) as average_rating, " +
                    "COALESCE(t1.reviews_count, CAST(NULL AS INTEGER)) as reviews_count, " +
                    "COALESCE(t1.street_address, CAST(NULL AS VARCHAR)) as street_address, " +
                    "COALESCE(t1.city, CAST(NULL AS VARCHAR)) as city, " +
                    "COALESCE(t1.state, CAST(NULL AS VARCHAR)) as state, " +
                    "COALESCE(t1.zip, CAST(NULL AS VARCHAR)) as zip, " +
                    "COALESCE(lc.scraped_at, t1.created_at) as list_found_at, " +
                    "COALESCE(lc.details_at, t1.updated_at) as details_found_at, " +
                    "COALESCE(lc.enqueued_at, CAST(NULL AS VARCHAR)) as enqueued_at, " +
                    "COALESCE(lc.enriched_at, CAST(NULL AS VARCHAR)) as last_enriched " +
                    f"FROM items_checkpoint t1 FULL OUTER JOIN items_cache t2 ON {t1_slug} = t2.slug " +
                    "LEFT JOIN items_lifecycle lc ON (COALESCE(t1.place_id, CAST(NULL AS VARCHAR)) = lc.place_id)")

                _last_cache_mtime = current_cache_mtime
                _last_checkpoint_mtime = current_checkpoint_mtime
                _last_lifecycle_mtime = current_lifecycle_mtime
                _last_campaign = campaign
                logger.debug(f"Rebuilt DuckDB search sources in {time.perf_counter() - t0:.4f}s")
            
            # 3. Build Query
            t0 = time.perf_counter()
            sql = "SELECT type, name, slug, domain, email, phone_number, tags, display, average_rating, reviews_count, street_address, city, state, zip, list_found_at, details_found_at, enqueued_at, last_enriched FROM items WHERE 1=1"
            params: List[Any] = []

            if item_type:
                sql += " AND type = ?"
                params.append(item_type)

            if filters:
                if filters.get("has_contact_info"):
                    sql += " AND ((email IS NOT NULL AND email != '' AND email != 'null') OR (phone_number IS NOT NULL AND phone_number != '' AND phone_number != 'null'))"
                elif filters.get("has_email_and_phone"):
                    sql += " AND email IS NOT NULL AND email != '' AND email != 'null' AND phone_number IS NOT NULL AND phone_number != '' AND phone_number != 'null'"
                
                if filters.get("no_email"):
                    sql += " AND (email IS NULL OR email = '' OR email = 'null')"
                
                if filters.get("has_email"):
                    sql += " AND email IS NOT NULL AND email != '' AND email != 'null'"
                
                if filters.get("no_address"):
                    sql += " AND (street_address IS NULL OR street_address = '' OR street_address = 'null')"

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
                sql += " AND (lower(name) LIKE ? OR lower(slug) LIKE ? OR lower(domain) LIKE ? OR lower(email) LIKE ? OR lower(display) LIKE ?)"
                params.extend([query_pattern] * 5)
                
                # Restore tags search with safety
                if has_col("items", "tags"):
                    sql = sql[:-1] # Remove last ')'
                    sql += " OR array_to_string(tags, ',') LIKE ?)"
                    params.append(query_pattern)

            # Ordering
            if sort_by == "recent":
                sql += " ORDER BY last_modified DESC NULLS LAST"
            elif sort_by == "rating":
                sql += " ORDER BY average_rating DESC NULLS LAST, reviews_count DESC NULLS LAST"
            elif sort_by == "reviews":
                sql += " ORDER BY reviews_count DESC NULLS LAST"
            elif not search_query:
                sql += " ORDER BY name ASC"
            
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])

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
                unique_id=str(r[2]) if r[2] else str(r[1]) or "unknown",
                average_rating=float(r[8]) if r[8] is not None else None,
                reviews_count=int(r[9]) if r[9] is not None else None,
                street_address=str(r[10]) if r[10] else None,
                city=str(r[11]) if r[11] else None,
                state=str(r[12]) if r[12] else None,
                zip=str(r[13]) if r[13] else None,
                list_found_at=str(r[14]) if r[14] else None,
                details_found_at=str(r[15]) if r[15] else None,
                enqueued_at=str(r[16]) if r[16] else None,
                last_enriched=str(r[17]) if r[17] else None
            ))

        logger.debug(f"Fuzzy search '{search_query}' took {time.perf_counter() - start_total:.4f}s (query={t_query:.4f}s)")
        return final_items
