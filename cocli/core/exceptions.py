class EnrichmentError(Exception):
    """Base class for enrichment errors."""

class NavigationError(EnrichmentError):
    """Raised when navigation to the website fails."""
