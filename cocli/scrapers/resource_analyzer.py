import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Categories for the "Value-First" policy
NON_COMMERCIAL_CATEGORIES = [
    "park", "library", "recreation center", "public swimming pool", 
    "community garden", "museum", "art center", "historical landmark",
    "hiking area", "playground", "nature preserve", "botanical garden"
]

def is_likely_non_commercial(category: str) -> bool:
    if not category:
        return False
    cat_lower = category.lower()
    return any(c in cat_lower for c in NON_COMMERCIAL_CATEGORIES)

def analyze_resource_value(name: str, category: str, description: str, reviews: str) -> Dict[str, Any]:
    """
    Analyzes a resource to determine its fee structure and value for the "Value-First" policy.
    In a real implementation, this would call an LLM. For now, we use a rule-based heuristic.
    """
    analysis = {
        "is_value_resource": False,
        "fee_category": "unknown",
        "rationale": ""
    }
    
    # 1. Keyword-based heuristic (Search in description and reviews) - HIGHER PRIORITY
    content = (description + " " + reviews).lower()
    
    free_keywords = ["free entrance", "no fee", "public access", "community resource"]
    nominal_keywords = ["nominal fee", "$5", "$2", "small fee", "donation suggested", "entrance fee"]
    subscription_keywords = ["membership required", "subscription", "monthly fee", "private club"]

    if any(k in content for k in free_keywords):
        analysis["is_value_resource"] = True
        analysis["fee_category"] = "free"
        analysis["rationale"] = "Found keywords suggesting free access."
        return analysis
    elif any(k in content for k in nominal_keywords):
        analysis["is_value_resource"] = True
        analysis["fee_category"] = "nominal"
        analysis["rationale"] = "Found keywords suggesting a nominal fee."
        return analysis
    elif any(k in content for k in subscription_keywords):
        analysis["is_value_resource"] = False
        analysis["fee_category"] = "subscription"
        analysis["rationale"] = "Found keywords suggesting subscription/membership requirements."
        return analysis

    # 2. Category-based heuristic - FALLBACK
    if is_likely_non_commercial(category):
        analysis["is_value_resource"] = True
        analysis["fee_category"] = "free_or_nominal"
        analysis["rationale"] = f"Category '{category}' is typically public/non-commercial."
        return analysis
        
    return analysis
