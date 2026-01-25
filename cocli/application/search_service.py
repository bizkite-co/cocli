import duckdb
from typing import List, Optional
from cocli.core.cache import get_cached_items
from cocli.core.config import get_campaign
from cocli.core.exclusions import ExclusionManager
from cocli.models.search import SearchResult

def get_fuzzy_search_results(
    search_query: str = "",
    item_type: Optional[str] = None,
    campaign_name: Optional[str] = None,
    force_rebuild_cache: bool = False
) -> List[SearchResult]:
    """
    Provides fuzzy search results for companies and people, respecting campaign context.
    Uses DuckDB for efficient querying of the fz cache.

    Args:
        search_query: The search string to filter items.
        item_type: Optional; "company" or "person" to filter by type.
        campaign_name: Optional; The name of the active campaign.
        force_rebuild_cache: Whether to force a rebuild of the fz cache.

    Returns:
        A list of Pydantic SearchResult objects, each representing a filtered item.
    """
    campaign = campaign_name or get_campaign() # Use provided campaign or get from context
    
    # Ensure cache is built and valid. get_cached_items handles the rebuild logic.
    # We get the list of dicts directly, bypassing file read ambiguity in DuckDB
    items = get_cached_items(
        filter_str=None,
        campaign=campaign,
        force_rebuild=force_rebuild_cache
    )

    if not items:
        return []

    try:
        con = duckdb.connect(database=':memory:')
        
        # Create table with explicit schema
        con.execute("""
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
        
        # Prepare data for insertion
        # We need to ensure tags is a list, and handle potential None values for other fields
        rows = []
        for item in items:
            rows.append((
                item.get('type'),
                item.get('name'),
                item.get('slug'),
                item.get('domain'),
                item.get('email'),
                item.get('tags', []), # Ensure list
                item.get('display')
            ))
            
        # Bulk insert
        con.executemany("INSERT INTO items VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
        
        # Base query
        sql = "SELECT * FROM items WHERE 1=1"

        # Apply item_type filter
        if item_type:
            sql += f" AND type = '{item_type}'"

        # Apply campaign exclusions
        if campaign:
            exclusion_manager = ExclusionManager(campaign=campaign)
            excluded_domains = [str(exc.domain) for exc in exclusion_manager.list_exclusions() if exc.domain]
            excluded_slugs = [str(exc.company_slug) for exc in exclusion_manager.list_exclusions() if exc.company_slug]
            
            if excluded_domains:
                domains_str = ", ".join([f"'{d}'" for d in excluded_domains])
                sql += f" AND (domain IS NULL OR domain NOT IN ({domains_str}))"
            if excluded_slugs:
                slugs_str = ", ".join([f"'{s}'" for s in excluded_slugs])
                sql += f" AND (slug IS NULL OR slug NOT IN ({slugs_str}))"

        # Apply search filter (case-insensitive substring match)
        if search_query:
            query_lower = search_query.lower()
            sql += f""" AND (
                lower(name) LIKE '%{query_lower}%'
                OR lower(slug) LIKE '%{query_lower}%'
                OR lower(domain) LIKE '%{query_lower}%'
                OR lower(email) LIKE '%{query_lower}%'
                OR lower(display) LIKE '%{query_lower}%'
                OR array_to_string(tags, ',') LIKE '%{query_lower}%'
            )"""

        results = con.execute(sql).fetchall()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"DuckDB search failed: {e}")
        return []

    # Map back to dicts and ensure unique IDs
    # DuckDB results are tuples: (type, name, slug, domain, email, tags, display)
    seen_ids = set()
    final_items = []
    for r in results:
        # r[5] is the tags field, typically a list in DuckDB Python client
        tags_list = r[5] if r[5] is not None else []

        item = {
            "type": r[0],
            "name": r[1],
            "slug": r[2],
            "domain": r[3],
            "email": r[4],
            "tags": tags_list,
            "display": r[6]
        }
        
        original_slug = item.get("slug") or "unknown"
        unique_id = original_slug
        counter = 1
        while unique_id in seen_ids:
            unique_id = f"{original_slug}-{counter}"
            counter += 1
        seen_ids.add(unique_id)
        item["unique_id"] = unique_id
        final_items.append(SearchResult(**item))

    return final_items