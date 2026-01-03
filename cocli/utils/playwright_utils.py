import logging
from playwright.async_api import BrowserContext, Request, Response

logger = logging.getLogger(__name__)

class BandwidthTracker:
    def __init__(self):
        self.total_bytes = 0
        self.request_count = 0

    def reset(self):
        self.total_bytes = 0
        self.request_count = 0

    def get_mb(self) -> float:
        return self.total_bytes / (1024 * 1024)

    def log_response(self, response: Response):
        self.request_count += 1
        # Try to get content-length from headers
        headers = response.headers
        length = headers.get("content-length")
        if length:
            self.total_bytes += int(length)
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
        
        async def intercept_request(request: Request):
            if request.resource_type in excluded_resource_types:
                await request.abort()
            else:
                await request.continue_()

        await context.route("**/*", intercept_request)

    if track_bandwidth:
        context.on("response", lambda response: tracker.log_response(response))

    return tracker
