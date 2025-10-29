from typing import List, Dict, Any, Optional
from cocli.core.cache import get_cached_items
from cocli.core.config import get_campaign
from cocli.core.exclusions import ExclusionManager # Assuming this is part of core logic

def get_fuzzy_search_results(
    search_query: str = "",
    item_type: Optional[str] = None,
    campaign_name: Optional[str] = None,
    force_rebuild_cache: bool = False
) -> List[Dict[str, Any]]:
    """
    Provides fuzzy search results for companies and people, respecting campaign context.

    Args:
        search_query: The search string to filter items.
        item_type: Optional; "company" or "person" to filter by type.
        campaign_name: Optional; The name of the active campaign.
        force_rebuild_cache: Whether to force a rebuild of the fz cache.

    Returns:
        A list of dictionaries, each representing a filtered item.
    """
    campaign = campaign_name or get_campaign() # Use provided campaign or get from context
    
    all_searchable_items = get_cached_items(
        filter_str=None, # fz_utils handles filtering, not get_cached_items directly
        campaign=campaign,
        force_rebuild=force_rebuild_cache
    )

    # Apply item_type filter
    if item_type:
        all_searchable_items = [item for item in all_searchable_items if item.get("type") == item_type]

    # Apply campaign exclusions
    if campaign:
        exclusion_manager = ExclusionManager(campaign=campaign)
        all_searchable_items = [
            item for item in all_searchable_items
            if not (item.get("type") == "company" and item.get("domain") is not None and exclusion_manager.is_excluded(str(item.get("domain"))))
        ]

    # Apply fuzzy search filter (case-insensitive)
    if search_query:
        search_query_lower = search_query.lower()
        all_searchable_items = [
            item for item in all_searchable_items
            if any(
                isinstance(value, str) and search_query_lower in value.lower()
                for value in item.values()
            )
        ]
    
    # Ensure unique IDs for ListItem (this part is specific to TUI, but can be handled here
    # if the service layer is aware of the presentation layer's needs, or in the TUI itself)
    seen_ids = set()
    final_items = []
    for item in all_searchable_items:
        original_slug = item.get("slug", "")
        unique_id = original_slug
        counter = 1
        while unique_id in seen_ids:
            unique_id = f"{original_slug}-{counter}"
            counter += 1
        seen_ids.add(unique_id)
        item["unique_id"] = unique_id
        final_items.append(item)

    return final_items