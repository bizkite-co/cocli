from typing import List, Dict, Any, Optional
# from cocli.core.cache import get_cached_items # Removed
# from cocli.core.config import get_campaign # Removed
# import hashlib # Removed

from cocli.application.search_service import get_fuzzy_search_results # New import

def get_filtered_items_from_fz(search_query: str = "", item_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Fetches and filters items using the fz caching mechanism.

    Args:
        search_query: The search string to filter items.
        item_type: Optional; "company" or "person" to filter by type.

    Returns:
        A list of dictionaries, each representing a filtered item.
    """
    # Delegate to the search_service
    return get_fuzzy_search_results(search_query=search_query, item_type=item_type)