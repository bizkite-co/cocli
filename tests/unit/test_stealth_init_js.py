"""Guards cocli/utils/stealth_init.js against silent parse failures.

The script is injected into every Playwright BrowserContext via
add_init_script(), which does not surface JS syntax errors back to
Python - a broken script just never runs in the browser. That's exactly
what happened when this file was a Python triple-quoted string using
'#' for comments (not valid JS): the whole fingerprint-masking script
silently no-opped on every gm-list scrape for months. This test runs
the file through the Node binary Playwright already bundles (no new
toolchain dependency) so a syntax error fails CI instead of the browser.
"""

import subprocess
from pathlib import Path

from playwright._impl._driver import compute_driver_executable

STEALTH_JS_PATH = Path(__file__).parents[2] / "cocli" / "utils" / "stealth_init.js"


def test_stealth_init_js_is_valid_syntax() -> None:
    node_executable, _ = compute_driver_executable()

    result = subprocess.run(
        [node_executable, "--check", str(STEALTH_JS_PATH)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"cocli/utils/stealth_init.js has a JS syntax error:\n{result.stderr}"
    )
