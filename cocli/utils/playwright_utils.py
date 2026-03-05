# POLICY: frictionless-data-policy-enforcement
import logging
from playwright.async_api import BrowserContext
from .headers import ANTI_BOT_HEADERS

logger = logging.getLogger(__name__)

async def setup_stealth_context(
    context: BrowserContext,
) -> None:
    """
    Applies absolute high-fidelity anti-bot measures to a Playwright context.
    Uses centralized project ANTI_BOT_HEADERS.
    """
    # 1. Comprehensive Stealth Script (Fingerprint Masking)
    await context.add_init_script("""
        # Mask WebDriver
        Object.defineProperty(navigator, 'webdriver', { get: () => false });
        
        # Mask Languages & Platform
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
        
        # Mask Hardware Specs
        Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 16 });
        Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
        
        # WebGL Unmasking (CRITICAL for Maps)
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) return 'Google Inc. (Intel)';
            if (parameter === 37446) return 'ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0)';
            return getParameter.apply(this, arguments);
        };

        if (window.WebGL2RenderingContext) {
            const getParameter2 = WebGL2RenderingContext.prototype.getParameter;
            WebGL2RenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) return 'Google Inc. (Intel)';
                if (parameter === 37446) return 'ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0)';
                return getParameter2.apply(this, arguments);
            };
        }

        const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function(type) {
            return originalToDataURL.apply(this, arguments);
        };
    """)

    # 2. Set Centralized Extra Headers
    await context.set_extra_http_headers(ANTI_BOT_HEADERS)

async def setup_optimized_context(
    context: BrowserContext, 
) -> None:
    """
    No-op for maximum fidelity. 
    Efficiency considerations are strictly prohibited during this troubleshooting phase.
    """
    pass
