# POLICY: frictionless-data-policy-enforcement (See docs/FRICTIONLESS_DATA_POLICY_ENFORCEMENT.md)
from __future__ import annotations
import duckdb
import os
import logging
import time
import threading
import json
import tempfile
from pathlib import Path
from typing import Optional, Any, cast
from cocli.core.cache import get_cache_path, CACHE_FILE_NAME
from cocli.core.config import get_campaign
from cocli.core.exclusions import list_all_exclusions
from cocli.models.search import SearchResult
from cocli.models.company_name import CompanyName
from cocli.models.company_address import CompanyAddress
from cocli.models.phone import PhoneNumber
from cocli.utils.duckdb_utils import (
    get_duckdb_schema_from_datapackage,
    load_usv_to_duckdb,
)
from cocli.models.campaigns.indexes.google_maps_place import GoogleMapsPlace
from cocli.models.campaigns.indexes.email import EmailEntry

logger = logging.getLogger(__name__)


class SearchResultsList(list[SearchResult]):
    """Subclass of list that allows custom attributes such as total_count."""

    total_count: int = 0




def _get_compacted_fallback_columns() -> dict[str, str]:
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


_FRICTIONLESS_TO_DUCK: dict[str, str] = {
    "string": "VARCHAR",
    "integer": "BIGINT",
    "number": "DOUBLE",
    "datetime": "VARCHAR",
    "boolean": "BOOLEAN",
}


def _columns_from_datapackage_fields(fields: list[dict[str, Any]]) -> dict[str, str]:
    """Map Frictionless field defs to DuckDB column types."""
    return {
        str(field["name"]): _FRICTIONLESS_TO_DUCK.get(
            str(field.get("type", "string")), "VARCHAR"
        )
        for field in fields
    }


def _sql_present(column: str) -> str:
    """SQL predicate: column has a real (non-empty, non-'null') value."""
    return (
        f"({column} IS NOT NULL AND CAST({column} AS VARCHAR) != '' "
        f"AND lower(CAST({column} AS VARCHAR)) != 'null')"
    )


def _dir_mtime(path: Optional[Path]) -> float:
    if path and path.exists():
        return os.path.getmtime(path)
    return -1.0


def _load_email_index(
    con: duckdb.DuckDBPyConnection, emails_root: Optional[Path]
) -> None:
    """Load emails shards + inbox using EmailEntry datapackage as schema authority."""
    columns = _columns_from_datapackage_fields(EmailEntry.get_datapackage_fields())
    if emails_root:
        dp_path = emails_root / "datapackage.json"
        if dp_path.exists():
            try:
                columns = get_duckdb_schema_from_datapackage(dp_path)
            except Exception as e:
                logger.warning(f"FDPE: emails datapackage unreadable ({e}); using model")

    cols_sql = ", ".join(f'"{name}" {dtype}' for name, dtype in columns.items())
    con.execute("DROP TABLE IF EXISTS items_emails")
    con.execute("DROP TABLE IF EXISTS items_emails_by_slug")
    con.execute("DROP TABLE IF EXISTS items_emails_by_domain")

    files: list[str] = []
    if emails_root and emails_root.exists():
        shards_dir = emails_root / "shards"
        inbox_dir = emails_root / "inbox"
        if shards_dir.exists():
            files.extend(str(p) for p in shards_dir.glob("*.usv") if p.is_file())
        if inbox_dir.exists():
            files.extend(str(p) for p in inbox_dir.rglob("*.usv") if p.is_file())

    if not files:
        con.execute(f"CREATE TABLE items_emails ({cols_sql})")
    else:
        columns_def = ", ".join(
            f"\"{name}\": '{dtype}'" for name, dtype in columns.items()
        )
        cast_sql = ", ".join(
            f'TRY_CAST("{name}" AS {dtype}) AS "{name}"'
            for name, dtype in columns.items()
        )
        quoted = ", ".join("'" + p.replace("'", "''") + "'" for p in files)
        try:
            con.execute(f"""
                CREATE TABLE items_emails AS
                SELECT {cast_sql}
                FROM read_csv([{quoted}], delim='\x1f', header=False, auto_detect=False,
                              columns={{{columns_def}}}, quote='', escape='',
                              null_padding=True, union_by_name=True)
            """)
        except Exception as e:
            logger.error(f"FDPE: failed to load email index: {e}")
            con.execute(f"CREATE TABLE items_emails ({cols_sql})")

    con.execute("""
        CREATE TABLE items_emails_by_slug AS
        SELECT company_slug AS slug, MIN(email) AS email
        FROM items_emails
        WHERE company_slug IS NOT NULL AND TRIM(CAST(company_slug AS VARCHAR)) != ''
        GROUP BY company_slug
    """)
    con.execute("""
        CREATE TABLE items_emails_by_domain AS
        SELECT domain, MIN(email) AS email
        FROM items_emails
        WHERE domain IS NOT NULL AND TRIM(CAST(domain AS VARCHAR)) != ''
        GROUP BY domain
    """)


# Module-level cache for DuckDB connection and state
_con: Optional[duckdb.DuckDBPyConnection] = None
_last_cache_mtime: float = -1.0
_last_checkpoint_mtime: float = -1.0
_last_venue_mtime: float = -1.0
_last_lifecycle_mtime: float = -1.0
_last_to_call_mtime: float = -1.0
_last_to_call_invalid_mtime: float = -1.0
_last_email_mtime: float = -1.0
_last_campaign: Optional[str] = None
_lock = threading.RLock()

# Cache for template counts: { campaign_name: (timestamp, counts_dict) }
_counts_cache: dict[str, tuple[float, dict[str, int]]] = {}
_COUNTS_CACHE_TTL = 300  # 5 minutes


def get_template_counts(campaign_name: Optional[str] = None) -> dict[str, int]:
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

                email_sql = _sql_present("email")
                phone_sql = _sql_present("phone_number")
                addr_sql = _sql_present("street_address")
                row = _con.execute(f"""
                    SELECT
                      COUNT(*) FILTER (WHERE type = 'company'),
                      COUNT(*) FILTER (WHERE type = 'company' AND is_to_call = TRUE),
                      COUNT(*) FILTER (WHERE type = 'company' AND is_invalid = TRUE),
                      COUNT(*) FILTER (WHERE type = 'company' AND {email_sql}),
                      COUNT(*) FILTER (WHERE type = 'company' AND NOT {email_sql}),
                      COUNT(*) FILTER (
                        WHERE type = 'company' AND {email_sql} AND {phone_sql}
                      ),
                      COUNT(*) FILTER (WHERE type = 'company' AND NOT {addr_sql}),
                      COUNT(*) FILTER (
                        WHERE type = 'company' AND average_rating >= 4.0
                      ),
                      COUNT(*) FILTER (
                        WHERE type = 'company' AND reviews_count >= 10
                      ),
                      COUNT(*) FILTER (WHERE type = 'venue')
                    FROM items
                """).fetchone()
                if row:
                    counts["tpl_all"] = int(row[0] or 0)
                    counts["tpl_to_call"] = int(row[1] or 0)
                    counts["tpl_invalid"] = int(row[2] or 0)
                    counts["tpl_with_email"] = int(row[3] or 0)
                    counts["tpl_no_email"] = int(row[4] or 0)
                    counts["tpl_actionable"] = int(row[5] or 0)
                    counts["tpl_no_address"] = int(row[6] or 0)
                    counts["tpl_top_rated"] = int(row[7] or 0)
                    counts["tpl_most_reviewed"] = int(row[8] or 0)
                    counts["tpl_leads"] = int(row[0] or 0)
                    counts["tpl_venues"] = int(row[9] or 0)

                building: set[str] = getattr(get_fuzzy_search_results, "_building", set())
                if campaign not in building:
                    _counts_cache[campaign] = (now, counts)
            except Exception as e:
                logger.error(f"Failed to calculate template counts: {e}")

    return counts


def get_fuzzy_search_results(
    search_query: str = "",
    campaign_name: Optional[str] = None,
    item_type: Optional[str] = None,
    limit: int = 500,
    filters: Optional[dict[str, Any]] = None,
    force_rebuild_cache: bool = False,
    offset: int = 0,
    sort_by: Optional[str] = None,
) -> list[SearchResult]:
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
        _last_to_call_invalid_mtime, \
        _last_email_mtime, \
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
    to_call_invalid_pending_dir = None
    emails_root = None

    if campaign:
        campaign_node = paths.campaign(campaign)
        checkpoint_path = campaign_node.index("google_maps_prospects").checkpoint
        venue_checkpoint_path = (
            campaign_node.index("google_maps_venues").path / "venues.checkpoint.usv"
        )
        lifecycle_path = campaign_node.lifecycle
        lifecycle_dp = campaign_node.path / "indexes" / "lifecycle" / "datapackage.json"
        to_call_pending_dir = paths.queue(campaign, "to-call") / "pending"
        to_call_invalid_pending_dir = (
            paths.queue(campaign, "to-call-invalid") / "pending"
        )
        emails_root = campaign_node.index("emails").path

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
                        with _lock:
                            global _last_cache_mtime
                            _last_cache_mtime = -1.0
                            if campaign in _counts_cache:
                                del _counts_cache[campaign]
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
        current_to_call_invalid_mtime = (
            os.path.getmtime(to_call_invalid_pending_dir)
            if to_call_invalid_pending_dir and to_call_invalid_pending_dir.exists()
            else -1.0
        )
        current_email_mtime = max(
            _dir_mtime(emails_root / "shards" if emails_root else None),
            _dir_mtime(emails_root / "inbox" if emails_root else None),
            _dir_mtime(emails_root),
        )

        try:
            if _con is None:
                _con = duckdb.connect(database=":memory:")
                _last_cache_mtime = -1.0
                _last_checkpoint_mtime = -1.0
                _last_venue_mtime = -1.0
                _last_lifecycle_mtime = -1.0
                _last_to_call_mtime = -1.0
                _last_to_call_invalid_mtime = -1.0
                _last_email_mtime = -1.0

            if (
                _last_cache_mtime != current_cache_mtime
                or _last_checkpoint_mtime != current_checkpoint_mtime
                or _last_venue_mtime != current_venue_mtime
                or _last_campaign != campaign
                or _last_lifecycle_mtime != current_lifecycle_mtime
                or _last_to_call_mtime != current_to_call_mtime
                or _last_to_call_invalid_mtime != current_to_call_invalid_mtime
                or _last_email_mtime != current_email_mtime
            ):
                _con.execute("DROP VIEW IF EXISTS items")
                for table in [
                    "items_cache",
                    "items_checkpoint",
                    "items_prospects",
                    "items_venues",
                    "items_lifecycle",
                    "items_to_call",
                    "items_to_call_invalid",
                    "items_compacted",
                    "items_emails",
                    "items_emails_by_slug",
                    "items_emails_by_domain",
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
                    # A pending task with a future callback_at is a
                    # scheduled follow-up, not due yet (Mark, 2026-09-01:
                    # scheduled/ used to be a separate directory nothing
                    # ever read back, so follow-ups silently vanished -
                    # merged into pending/ with callback_at as the due date
                    # instead). Only surface tasks that are actually due.
                    from cocli.models.campaigns.queues.to_call import ToCallTask
                    from datetime import datetime, UTC

                    now = datetime.now(UTC)
                    items = []
                    for fname in os.listdir(to_call_pending_dir):
                        if not fname.endswith(".usv"):
                            continue
                        slug = fname.replace(".usv", "")
                        try:
                            content = (to_call_pending_dir / fname).read_text()
                            task = ToCallTask.from_usv(content)
                            due = task.callback_at is None or task.callback_at <= now
                        except Exception:
                            # Malformed/unparsable file - fall back to the
                            # previous filename-only behavior (due now)
                            # rather than silently dropping it.
                            due = True
                        if due:
                            items.append([slug])
                    if items:
                        _con.executemany("INSERT INTO items_to_call VALUES (?)", items)

                _con.execute("CREATE TABLE items_to_call_invalid (slug VARCHAR)")
                if to_call_invalid_pending_dir and to_call_invalid_pending_dir.exists():
                    invalid_items = [
                        [fname.replace(".usv", "")]
                        for fname in os.listdir(to_call_invalid_pending_dir)
                        if fname.endswith(".usv")
                    ]
                    if invalid_items:
                        _con.executemany(
                            "INSERT INTO items_to_call_invalid VALUES (?)",
                            invalid_items,
                        )

                _load_email_index(_con, emails_root)

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

                EMAIL_FROM_CACHE = (
                    "t2.email"
                    if table_has_col("items_cache", "email")
                    else "CAST(NULL AS VARCHAR)"
                )
                EMAIL_FROM_CHECKPOINT = (
                    "t1.email"
                    if table_has_col("items_checkpoint", "email")
                    else "CAST(NULL AS VARCHAR)"
                )
                STREET_FROM_COMPACTED = (
                    "compacted.street_address"
                    if table_has_col("items_compacted", "street_address")
                    else "CAST(NULL AS VARCHAR)"
                )
                STREET_FROM_CHECKPOINT = (
                    "t1.street_address"
                    if table_has_col("items_checkpoint", "street_address")
                    else "CAST(NULL AS VARCHAR)"
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
                        COALESCE(e_slug.email, e_dom.email, {EMAIL_FROM_CACHE}, {EMAIL_FROM_CHECKPOINT}) as email,
                        COALESCE(compacted.phone, t1.phone, t2.phone_number) as phone_number,
                        COALESCE(string_to_array(t2.tags, ';'), string_to_array(t1.keyword, ';'), CAST([] AS VARCHAR[])) as tags,
                        COALESCE(t2.display, 'COMPANY:' || COALESCE(t1.name, t2.name)) as display,
                        COALESCE(t1.updated_at, CAST(NULL AS VARCHAR)) as last_modified,
                        COALESCE({RATING_FROM_CHECKPOINT}, {RATING_FROM_CACHE}) as average_rating,
                        COALESCE({REVIEWS_FROM_CHECKPOINT}, {REVIEWS_FROM_CACHE}) as reviews_count,
                        COALESCE({STREET_FROM_COMPACTED}, {STREET_FROM_CHECKPOINT}) as street_address,
                        COALESCE(t1.city, CAST(NULL AS VARCHAR)) as city,
                        COALESCE(t1.state, CAST(NULL AS VARCHAR)) as state,
                        COALESCE(t1.zip, CAST(NULL AS VARCHAR)) as zip,
                        COALESCE({lc_scraped}, t1.created_at) as list_found_at,
                        COALESCE({lc_details}, t1.updated_at) as details_found_at,
                        COALESCE({lc_enqueued}, CAST(NULL AS VARCHAR)) as enqueued_at,
                        COALESCE({lc_enriched}, CAST(NULL AS VARCHAR)) as last_enriched,
                        CASE WHEN tc.slug IS NOT NULL THEN TRUE ELSE FALSE END as is_to_call,
                        CASE WHEN tci.slug IS NOT NULL THEN TRUE ELSE FALSE END as is_invalid
                    FROM items_checkpoint t1 
                    LEFT JOIN items_compacted compacted ON t1.place_id = compacted.place_id
                    FULL OUTER JOIN items_cache t2 ON t1.slug = t2.slug
                    LEFT JOIN items_lifecycle lc ON t1.place_id = lc.place_id
                    LEFT JOIN items_to_call tc ON COALESCE(t1.slug, t2.slug) = tc.slug
                    LEFT JOIN items_to_call_invalid tci
                        ON COALESCE(t1.slug, t2.slug) = tci.slug
                    LEFT JOIN items_emails_by_slug e_slug
                        ON COALESCE(t1.slug, t2.slug) = e_slug.slug
                    LEFT JOIN items_emails_by_domain e_dom
                        ON COALESCE(t1.domain, t2.domain) = e_dom.domain
                    ORDER BY slug, last_modified DESC NULLS LAST
                """)

                _last_cache_mtime = current_cache_mtime
                _last_checkpoint_mtime = current_checkpoint_mtime
                _last_venue_mtime = current_venue_mtime
                _last_lifecycle_mtime = current_lifecycle_mtime
                _last_to_call_mtime = current_to_call_mtime
                _last_to_call_invalid_mtime = current_to_call_invalid_mtime
                _last_email_mtime = current_email_mtime
                _last_campaign = campaign
                if campaign in _counts_cache:
                    del _counts_cache[campaign]

            # 3. Build Query
            sql = "SELECT type, name, slug, domain, email, phone_number, tags, display, average_rating, reviews_count, street_address, city, state, zip, list_found_at, details_found_at, enqueued_at, last_enriched FROM items WHERE 1=1"
            params: list[Any] = []

            if item_type:
                sql += " AND type = ?"
                params.append(item_type)

            if filters:
                email_sql = _sql_present("email")
                phone_sql = _sql_present("phone_number")
                addr_sql = _sql_present("street_address")
                if filters.get("has_contact_info"):
                    sql += f" AND ({email_sql} OR {phone_sql})"
                if filters.get("has_email_and_phone"):
                    sql += f" AND {email_sql} AND {phone_sql}"
                if filters.get("has_email"):
                    sql += f" AND {email_sql}"
                if filters.get("no_email"):
                    sql += f" AND NOT {email_sql}"
                if filters.get("no_address"):
                    sql += f" AND NOT {addr_sql}"
                if filters.get("to_call"):
                    sql += " AND is_to_call = TRUE"
                if filters.get("invalid"):
                    sql += " AND is_invalid = TRUE"

            if search_query:
                sql += " AND (name ILIKE ? OR slug ILIKE ? OR array_to_string(tags, ',') ILIKE ?)"
                q = f"%{search_query}%"
                params.extend([q, q, q])

            if sort_by == "recent":
                sql += " ORDER BY last_modified DESC NULLS LAST, name ASC"
            elif sort_by == "rating":
                sql += " ORDER BY average_rating DESC NULLS LAST, reviews_count DESC NULLS LAST"
            elif sort_by == "reviews":
                sql += " ORDER BY reviews_count DESC NULLS LAST, average_rating DESC NULLS LAST"
            elif not search_query:
                sql += " ORDER BY name ASC"

            # Calculate total count of matching items before pagination
            total_matching = 0
            try:
                count_res = _con.execute(f"SELECT COUNT(*) FROM ({sql})", params).fetchone()
                if count_res:
                    total_matching = int(count_res[0] or 0)
            except Exception:
                total_matching = 0

            sql_paginated = f"{sql} LIMIT {limit} OFFSET {offset}"
            res = _con.execute(sql_paginated, params).fetchall()

            # 4. Filter Exclusions
            # Invalid list IS the exclusion/review pile — do not hide those rows.
            skip_exclusions = bool(filters and filters.get("invalid"))
            excluded_slugs: set[str] = set()
            excluded_domains: set[str] = set()
            if not skip_exclusions:
                exclusions = list_all_exclusions(campaign or "")
                excluded_slugs = {e.company_slug for e in exclusions if e.company_slug}
                excluded_domains = {e.domain for e in exclusions if e.domain}

            final_items = SearchResultsList()
            for r in res:
                slug = str(r[2])
                domain = str(r[3]) if r[3] else None
                if slug in excluded_slugs or (domain and domain in excluded_domains):
                    continue

                final_items.append(
                    SearchResult(
                        unique_id=slug,
                        type=str(r[0]),
                        name=CompanyName(str(r[1])) if r[1] else None,
                        slug=slug,
                        domain=domain,
                        email=str(r[4]) if r[4] else None,
                        phone_number=PhoneNumber.validate(str(r[5])) if r[5] else None,
                        tags=cast(list[str], r[6]) if r[6] else [],
                        display=str(r[7]),
                        average_rating=float(r[8]) if r[8] else None,
                        reviews_count=int(r[9]) if r[9] else None,
                        street_address=CompanyAddress(str(r[10])) if r[10] else None,
                        city=str(r[11]) if r[11] else None,
                        state=str(r[12]) if r[12] else None,
                        zip=str(r[13]) if r[13] else None,
                        list_found_at=str(r[14]) if r[14] else None,
                        details_found_at=str(r[15]) if r[15] else None,
                        enqueued_at=str(r[16]) if r[16] else None,
                        last_enriched=str(r[17]) if r[17] else None,
                    )
                )

            final_items.total_count = total_matching
            return final_items

        except Exception as e:
            logger.error(f"FDPE: DuckDB search failed: {e}")
            import traceback

            logger.debug(traceback.format_exc())
            return SearchResultsList()

