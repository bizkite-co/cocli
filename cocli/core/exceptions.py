class EnrichmentError(Exception):
    """Base class for enrichment errors."""
    pass

class NavigationError(EnrichmentError):
    """Raised when navigation to the website fails."""
    pass
