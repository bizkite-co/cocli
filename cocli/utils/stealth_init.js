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

// Mask Plugins - a fresh Playwright/Chromium context reports an EMPTY
// navigator.plugins array; every real Chrome/Edge install reports the
// built-in PDF viewer entries. An empty plugins array is one of the
// oldest, most commonly checked automation "tells" (2026-09-17,
// alliedwealth.com SiteGround bot-challenge investigation - added
// alongside window.chrome below, the two other checklist items this
// script was missing next to the webdriver/languages/WebGL masking
// above).
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const pluginData = [
            { name: 'PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'Microsoft Edge PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'WebKit built-in PDF', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
        ];
        const plugins = pluginData.map((p) => ({
            name: p.name,
            filename: p.filename,
            description: p.description,
            length: 1,
        }));
        Object.setPrototypeOf(plugins, PluginArray.prototype);
        return plugins;
    },
});

// Mask window.chrome - real Chrome/Edge exposes this runtime object;
// bare automated Chromium often lacks it entirely.
if (!window.chrome) {
    window.chrome = { runtime: {} };
}
