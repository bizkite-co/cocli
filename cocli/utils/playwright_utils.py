import logging
from playwright.async_api import BrowserContext, Response, Route

logger = logging.getLogger(__name__)

class BandwidthTracker:
    def __init__(self) -> None:
        self.total_bytes = 0
        self.request_count = 0

    def reset(self) -> None:
        self.total_bytes = 0
        self.request_count = 0

    def get_mb(self) -> float:
        return self.total_bytes / (1024 * 1024)

    def log_response(self, response: Response) -> None:
        self.request_count += 1
        # Try to get content-length from headers
        headers = response.headers
        length = headers.get("content-length")
        if length:
            try:
                self.total_bytes += int(length)
            except ValueError:
                pass
        else:
            # Fallback: Approximate from body size if available (optional, can be expensive)
            pass

async def setup_optimized_context(
    context: BrowserContext, 
    block_resources: bool = True,
    track_bandwidth: bool = True
) -> BandwidthTracker:
    """
    Configures a Playwright context with resource blocking and bandwidth tracking.
    """
    tracker = BandwidthTracker()

    if block_resources:
        # Block unnecessary resources to save bandwidth and CPU
        excluded_resource_types = ["image", "media", "font", "stylesheet"]
        
        async def intercept_request(route: Route) -> None:
            request = route.request
            if request.resource_type in excluded_resource_types:
                await route.abort()
            else:
                await route.continue_()

        await context.route("**/*", intercept_request)

    if track_bandwidth:
        context.on("response", lambda response: tracker.log_response(response))

    return tracker
