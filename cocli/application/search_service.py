# POLICY: frictionless-data-policy-enforcement (See docs/FRICTIONLESS_DATA_POLICY_ENFORCEMENT.md)
import duckdb
import os
import logging
import time
import threading
import json
import tempfile
from pathlib import Path
from typing import List, Optional, Any, cast, Dict
from cocli.core.cache import get_cache_path, CACHE_FILE_NAME
from cocli.core.config import get_campaign
from cocli.core.exclusions import ExclusionManager
from cocli.models.search import SearchResult
from cocli.utils.duckdb_utils import load_usv_to_duckdb
from cocli.models.campaigns.indexes.google_maps_place import GoogleMapsPlace

logger = logging.getLogger(__name__)


def _get_compacted_fallback_columns() -> Dict[str, str]:
    """Return fallback columns for items_compacted table when no data exists."""
    return {
        "place_id": "VARCHAR",
        "slug": "VARCHAR",
        "phone": "VARCHAR",
        "average_rating": "VARCHAR",
        "reviews_count": "VARCHAR",
        "street_address": "VARCHAR",
        "city": "VARCHAR",
        "state": "VARCHAR",
        "zip": "VARCHAR",
    }


# Module-level cache for DuckDB connection and state
_con: Optional[duckdb.DuckDBPyConnection] = None
_last_cache_mtime: float = -1.0
_last_checkpoint_mtime: float = -1.0
_last_venue_mtime: float = -1.0
_last_lifecycle_mtime: float = -1.0
_last_to_call_mtime: float = -1.0
_last_campaign: Optional[str] = None
_lock = threading.RLock()

# Cache for template counts: { campaign_name: (timestamp, counts_dict) }
_counts_cache: Dict[str, tuple[float, Dict[str, int]]] = {}
_COUNTS_CACHE_TTL = 300  # 5 minutes


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

    # Non-blocking search trigger to ensure DuckDB is warm
    get_fuzzy_search_results("", item_type="company", campaign_name=campaign, limit=1)

    counts = {}
    with _lock:
        if _con:
            try:
                # Check if view exists before querying
                view_check = _con.execute(
                    "SELECT 1 FROM information_schema.views WHERE table_name = 'items'"
                ).fetchone()
                if not view_check:
                    return {}

                # Optimized count queries
                res_all = _con.execute("SELECT COUNT(*) FROM items").fetchone()
                counts["tpl_all"] = res_all[0] if res_all else 0

                res_call = _con.execute(
                    "SELECT COUNT(*) FROM items WHERE is_to_call = TRUE"
                ).fetchone()
                counts["tpl_to_call"] = res_call[0] if res_call else 0

                res_leads = _con.execute(
                    "SELECT COUNT(*) FROM items WHERE type = 'company'"
                ).fetchone()
                counts["tpl_leads"] = res_leads[0] if res_leads else 0

                res_venues = _con.execute(
                    "SELECT COUNT(*) FROM items WHERE type = 'venue'"
                ).fetchone()
                counts["tpl_venues"] = res_venues[0] if res_venues else 0

                _counts_cache[campaign] = (now, counts)
            except Exception as e:
                logger.error(f"Failed to calculate template counts: {e}")

    return counts


def get_fuzzy_search_results(
    search_query: str = "",
    campaign_name: Optional[str] = None,
    item_type: Optional[str] = None,
    limit: int = 500,
    filters: Optional[Dict[str, Any]] = None,
    force_rebuild_cache: bool = False,
    offset: int = 0,
    sort_by: Optional[str] = None,
) -> List[SearchResult]:
    """
    FDPE ENFORCEMENT: Provides fuzzy search results joined across multiple indices.
    """
    global \
        _con, \
        _last_cache_mtime, \
        _last_checkpoint_mtime, \
        _last_venue_mtime, \
        _last_lifecycle_mtime, \
        _last_to_call_mtime, \
        _last_campaign

    from cocli.core.paths import paths
    from cocli.core.cache import is_cache_valid, build_cache

    campaign = campaign_name or get_campaign()
    if campaign == "None":
        campaign = None

    cache_dir = get_cache_path(campaign=campaign)
    cache_file = cache_dir / CACHE_FILE_NAME
    cache_dp = cache_dir / "datapackage.json"

    checkpoint_path = None
    venue_checkpoint_path = None
    lifecycle_path = None
    lifecycle_dp = None
    to_call_pending_dir = None

    if campaign:
        campaign_node = paths.campaign(campaign)
        checkpoint_path = campaign_node.index("google_maps_prospects").checkpoint
        venue_checkpoint_path = (
            campaign_node.index("google_maps_venues").path / "venues.checkpoint.usv"
        )
        lifecycle_path = campaign_node.lifecycle
        lifecycle_dp = campaign_node.path / "indexes" / "lifecycle" / "datapackage.json"
        to_call_pending_dir = paths.queue(campaign, "to-call") / "pending"

    # 1. NON-BLOCKING CACHE REBUILD (Standard Pattern)
    is_test = os.getenv("COCLI_ENV") == "test"
    if force_rebuild_cache or not is_cache_valid(campaign=campaign):
        if is_test:
            build_cache(campaign=campaign)
        else:
            if not hasattr(get_fuzzy_search_results, "_building"):
                get_fuzzy_search_results._building = set()  # type: ignore
            if campaign not in get_fuzzy_search_results._building:  # type: ignore
                get_fuzzy_search_results._building.add(campaign)  # type: ignore

                def bg_rebuild() -> None:
                    try:
                        build_cache(campaign=campaign)
                    except Exception:
                        pass
                    finally:
                        get_fuzzy_search_results._building.remove(campaign)  # type: ignore

                threading.Thread(target=bg_rebuild, daemon=True).start()
        if not cache_file.exists() and not is_test:
            return []

    with _lock:
        current_cache_mtime = (
            os.path.getmtime(cache_file) if cache_file.exists() else -1.0
        )
        current_checkpoint_mtime = (
            os.path.getmtime(checkpoint_path)
            if checkpoint_path and checkpoint_path.exists()
            else -1.0
        )
        current_venue_mtime = (
            os.path.getmtime(venue_checkpoint_path)
            if venue_checkpoint_path and venue_checkpoint_path.exists()
            else -1.0
        )
        current_lifecycle_mtime = (
            os.path.getmtime(lifecycle_path)
            if lifecycle_path and lifecycle_path.exists()
            else -1.0
        )
        current_to_call_mtime = (
            os.path.getmtime(to_call_pending_dir)
            if to_call_pending_dir and to_call_pending_dir.exists()
            else -1.0
        )

        try:
            if _con is None:
                _con = duckdb.connect(database=":memory:")
                _last_cache_mtime = -1.0
                _last_checkpoint_mtime = -1.0
                _last_venue_mtime = -1.0
                _last_lifecycle_mtime = -1.0
                _last_to_call_mtime = -1.0

            if (
                _last_cache_mtime != current_cache_mtime
                or _last_checkpoint_mtime != current_checkpoint_mtime
                or _last_venue_mtime != current_venue_mtime
                or _last_campaign != campaign
                or _last_lifecycle_mtime != current_lifecycle_mtime
                or _last_to_call_mtime != current_to_call_mtime
            ):
                _con.execute("DROP VIEW IF EXISTS items")
                for table in [
                    "items_cache",
                    "items_checkpoint",
                    "items_prospects",
                    "items_venues",
                    "items_lifecycle",
                    "items_to_call",
                    "items_compacted",
                ]:
                    _con.execute(f"DROP TABLE IF EXISTS {table}")

                # A. Load Company Cache (Human Edits)
                load_usv_to_duckdb(_con, "items_cache", cache_file, cache_dp)

                # B. Load Google Maps Data (Prospects + Venues)
                # We use GoogleMapsPlace fields as the baseline for all map-based tables
                place_fields = GoogleMapsPlace.get_datapackage_fields()
                place_dp_mock = {"resources": [{"schema": {"fields": place_fields}}]}

                # Setup base datapackage for prospects and venues
                with tempfile.TemporaryDirectory() as tmp_dir:
                    base_dp = Path(tmp_dir) / "place_datapackage.json"
                    with open(base_dp, "w") as f:
                        json.dump(place_dp_mock, f)

                    if checkpoint_path and checkpoint_path.exists():
                        load_usv_to_duckdb(
                            _con, "items_prospects", checkpoint_path, base_dp
                        )
                    else:
                        load_usv_to_duckdb(
                            _con, "items_prospects", Path("/dev/null"), base_dp
                        )

                    # Load Compacted Data (Schema-Validated Source of Truth)
                    # ALWAYS run this to ensure items_compacted table exists, even with no campaign
                    if campaign:
                        compacted_path = (
                            paths.campaign(campaign).queue("gm-list").completed
                            / "results"
                            / "compacted.usv"
                        )
                        compacted_dp = compacted_path.parent / "datapackage.json"

                        # Ensure table always exists, even if file doesn't
                        if compacted_path.exists():
                            load_usv_to_duckdb(
                                _con,
                                "items_compacted",
                                compacted_path,
                                compacted_dp,
                            )
                        else:
                            # Create empty table with correct schema if file missing
                            columns = _get_compacted_fallback_columns()
                            cols_sql = ", ".join(
                                [f'"{name}" {dtype}' for name, dtype in columns.items()]
                            )
                            _con.execute(f"CREATE TABLE items_compacted ({cols_sql})")
                    else:
                        # Even with no campaign, create the table with fallback schema
                        columns = _get_compacted_fallback_columns()
                        cols_sql = ", ".join(
                            [f'"{name}" {dtype}' for name, dtype in columns.items()]
                        )
                        _con.execute(f"CREATE TABLE items_compacted ({cols_sql})")

                    has_v = False
                    if venue_checkpoint_path and venue_checkpoint_path.exists():
                        load_usv_to_duckdb(
                            _con, "items_venues", venue_checkpoint_path, base_dp
                        )
                        has_v = True
                    else:
                        load_usv_to_duckdb(
                            _con, "items_venues", Path("/dev/null"), base_dp
                        )

                    # Union Prospects and Venues into items_checkpoint
                    # MANDATE: Label all as 'company' for TUI visibility
                    _con.execute(
                        "CREATE TABLE items_checkpoint AS SELECT *, CAST('company' AS VARCHAR) as type FROM items_prospects"
                    )
                    if has_v:
                        _con.execute(
                            "INSERT INTO items_checkpoint SELECT *, CAST('company' AS VARCHAR) as type FROM items_venues"
                        )

                # C. Load Lifecycle & To-Call
                load_usv_to_duckdb(
                    _con,
                    "items_lifecycle",
                    lifecycle_path or Path("/dev/null"),
                    lifecycle_dp,
                )

                _con.execute("CREATE TABLE items_to_call (slug VARCHAR)")
                if to_call_pending_dir and to_call_pending_dir.exists():
                    items = [
                        [f.replace(".usv", "")]
                        for f in os.listdir(to_call_pending_dir)
                        if f.endswith(".usv")
                    ]
                    if items:
                        _con.executemany("INSERT INTO items_to_call VALUES (?)", items)

                # D. Unified Search View (Strict Schema Implementation)
                # We normalize column names to be robust across all data sources
                def table_has_col(table: str, col: str) -> bool:
                    try:
                        res = _con.execute(f"PRAGMA table_info('{table}')").fetchall()
                        return any(cast(str, c[1]).lower() == col.lower() for c in res)
                    except Exception:
                        return False

                # Rating and reviews from checkpoint (prioritizes compacted, falls back to checkpoint)
                # Priority: compacted > checkpoint
                RATING_FROM_CHECKPOINT = (
                    "COALESCE(TRY_CAST(compacted.average_rating AS DOUBLE), TRY_CAST(t1.average_rating AS DOUBLE))"
                    if (
                        table_has_col("items_checkpoint", "average_rating")
                        or table_has_col("items_compacted", "average_rating")
                    )
                    else "CAST(NULL AS DOUBLE)"
                )
                REVIEWS_FROM_CHECKPOINT = (
                    "COALESCE(TRY_CAST(compacted.reviews_count AS BIGINT), TRY_CAST(t1.reviews_count AS BIGINT))"
                    if (
                        table_has_col("items_checkpoint", "reviews_count")
                        or table_has_col("items_compacted", "reviews_count")
                    )
                    else "CAST(NULL AS BIGINT)"
                )

                # Rating and reviews from cache (human-edited company data)
                RATING_FROM_CACHE = (
                    "TRY_CAST(t2.average_rating AS DOUBLE)"
                    if table_has_col("items_cache", "average_rating")
                    else "CAST(NULL AS DOUBLE)"
                )
                REVIEWS_FROM_CACHE = (
                    "TRY_CAST(t2.reviews_count AS BIGINT)"
                    if table_has_col("items_cache", "reviews_count")
                    else "CAST(NULL AS BIGINT)"
                )

                lc_enqueued = (
                    "lc.enqueued_at"
                    if table_has_col("items_lifecycle", "enqueued_at")
                    else "CAST(NULL AS VARCHAR)"
                )
                lc_enriched = (
                    "lc.enriched_at"
                    if table_has_col("items_lifecycle", "enriched_at")
                    else "CAST(NULL AS VARCHAR)"
                )

                lc_scraped = (
                    "lc.scraped_at"
                    if table_has_col("items_lifecycle", "scraped_at")
                    else "lc.created_at"
                    if table_has_col("items_lifecycle", "created_at")
                    else "CAST(NULL AS VARCHAR)"
                )
                lc_details = (
                    "lc.details_at"
                    if table_has_col("items_lifecycle", "details_at")
                    else "lc.updated_at"
                    if table_has_col("items_lifecycle", "updated_at")
                    else "CAST(NULL AS VARCHAR)"
                )

                _con.execute(f"""
                    CREATE VIEW items AS 
                    SELECT DISTINCT ON (slug)
                        COALESCE(t1.slug, t2.slug) as slug,
                        COALESCE(t1.name, t2.name) as name,
                        COALESCE(t1.type, t2.type, CAST('company' AS VARCHAR)) as type,
                        COALESCE(t1.domain, t2.domain) as domain,
                        COALESCE(t2.email, t1.email) as email,
                        COALESCE(compacted.phone, t1.phone, t2.phone_number) as phone_number,
                        COALESCE(string_to_array(t2.tags, ';'), string_to_array(t1.keyword, ';'), CAST([] AS VARCHAR[])) as tags,
                        COALESCE(t2.display, 'COMPANY:' || COALESCE(t1.name, t2.name)) as display,
                        COALESCE(t1.updated_at, CAST(NULL AS VARCHAR)) as last_modified,
                        COALESCE({RATING_FROM_CHECKPOINT}, {RATING_FROM_CACHE}) as average_rating,
                        COALESCE({REVIEWS_FROM_CHECKPOINT}, {REVIEWS_FROM_CACHE}) as reviews_count,
                        COALESCE(t1.street_address, CAST(NULL AS VARCHAR)) as street_address,
                        COALESCE(t1.city, CAST(NULL AS VARCHAR)) as city,
                        COALESCE(t1.state, CAST(NULL AS VARCHAR)) as state,
                        COALESCE(t1.zip, CAST(NULL AS VARCHAR)) as zip,
                        COALESCE({lc_scraped}, t1.created_at) as list_found_at,
                        COALESCE({lc_details}, t1.updated_at) as details_found_at,
                        COALESCE({lc_enqueued}, CAST(NULL AS VARCHAR)) as enqueued_at,
                        COALESCE({lc_enriched}, CAST(NULL AS VARCHAR)) as last_enriched,
                        CASE WHEN tc.slug IS NOT NULL THEN TRUE ELSE FALSE END as is_to_call
                    FROM items_checkpoint t1 
                    LEFT JOIN items_compacted compacted ON t1.place_id = compacted.place_id
                    FULL OUTER JOIN items_cache t2 ON t1.slug = t2.slug
                    LEFT JOIN items_lifecycle lc ON t1.place_id = lc.place_id
                    LEFT JOIN items_to_call tc ON COALESCE(t1.slug, t2.slug) = tc.slug
                    ORDER BY slug, last_modified DESC NULLS LAST
                """)

                _last_cache_mtime = current_cache_mtime
                _last_checkpoint_mtime = current_checkpoint_mtime
                _last_venue_mtime = current_venue_mtime
                _last_lifecycle_mtime = current_lifecycle_mtime
                _last_to_call_mtime = current_to_call_mtime
                _last_campaign = campaign
                if campaign in _counts_cache:
                    del _counts_cache[campaign]

            # 3. Build Query
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
                if filters.get("to_call"):
                    sql += " AND is_to_call = TRUE"

            if search_query:
                sql += " AND (name ILIKE ? OR slug ILIKE ? OR array_to_string(tags, ',') ILIKE ?)"
                q = f"%{search_query}%"
                params.extend([q, q, q])

            sql += f" LIMIT {limit} OFFSET {offset}"
            res = _con.execute(sql, params).fetchall()

            # 4. Filter Exclusions
            exclusions = ExclusionManager(campaign or "").list_exclusions()
            excluded_slugs = {e.company_slug for e in exclusions if e.company_slug}
            excluded_domains = {e.domain for e in exclusions if e.domain}

            final_items = []
            for r in res:
                slug = str(r[2])
                domain = str(r[3]) if r[3] else None
                if slug in excluded_slugs or (domain and domain in excluded_domains):
                    continue

                final_items.append(
                    SearchResult(
                        unique_id=slug,
                        type=str(r[0]),
                        name=str(r[1]),
                        slug=slug,
                        domain=domain,
                        email=str(r[4]) if r[4] else None,
                        phone_number=str(r[5]) if r[5] else None,
                        tags=cast(List[str], r[6]) if r[6] else [],
                        display=str(r[7]),
                        average_rating=float(r[8]) if r[8] else None,
                        reviews_count=int(r[9]) if r[9] else None,
                        street_address=str(r[10]) if r[10] else None,
                        city=str(r[11]) if r[11] else None,
                        state=str(r[12]) if r[12] else None,
                        zip=str(r[13]) if r[13] else None,
                        list_found_at=str(r[14]) if r[14] else None,
                        details_found_at=str(r[15]) if r[15] else None,
                        enqueued_at=str(r[16]) if r[16] else None,
                        last_enriched=str(r[17]) if r[17] else None,
                    )
                )

            return final_items

        except Exception as e:
            logger.error(f"FDPE: DuckDB search failed: {e}")
            import traceback

            logger.debug(traceback.format_exc())
            return []
