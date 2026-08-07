// Comprehensive Stealth Script (Fingerprint Masking) injected via
// BrowserContext.add_init_script() before every page navigation. See
// setup_stealth_context() in playwright_utils.py.
//
// This previously lived as a Python triple-quoted string using '#' for
// comments. '#' is not a valid JS comment mid-script, so the whole init
// script silently failed to parse in the browser on every page load -
// none of the masking below ever ran. Keeping it as a real .js file lets
// a JS parser (see tests/unit/test_stealth_init_js.py, which runs the
// Node binary bundled with Playwright) catch that class of bug again.

// Mask WebDriver
Object.defineProperty(navigator, 'webdriver', { get: () => false });

// Mask Languages & Platform
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });

// Mask Hardware Specs
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 16 });
Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });

// WebGL Unmasking (CRITICAL for Maps)
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
