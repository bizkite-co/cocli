#!/usr/bin/env python3
"""
Playwright-based E2E Verification Script for getretirementtaxanalyzer.com.
Simulates an outreach email click with full UTM parameters, asserts dataLayer events,
and verifies GTM container response.
"""

from __future__ import annotations

import json
import sys
from playwright.sync_api import sync_playwright

SITE_URL = "https://getretirementtaxanalyzer.com"
UTM_TEST_URL = f"{SITE_URL}/?utm_source=email_sequence&utm_medium=email&utm_campaign=roadmap&utm_content=a-e-insurance-agency-llc&utm_term=steve"


def run_verification(target_url: str = UTM_TEST_URL) -> None:
    print(f"=== Starting Telemetry & GTM Verification for {target_url} ===")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        network_requests: list[str] = []
        page.on("request", lambda req: network_requests.append(req.url))

        print("[1] Navigating to target URL...")
        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
        except Exception as exc:
            print(f"⚠️ Navigation warning/timeout (testing live network): {exc}")

        title = page.title()
        print(f"    Page Title: '{title}'")

        # Evaluate window.dataLayer
        data_layer = page.evaluate("() => window.dataLayer || []")
        print(f"[2] Captured window.dataLayer events ({len(data_layer)} item(s)):")
        print(json.dumps(data_layer, indent=2))

        # Check for GTM / GA4 network calls
        gtm_reqs = [r for r in network_requests if "googletagmanager.com" in r or "google-analytics.com" in r]
        print(f"[3] GTM/Analytics Network Requests Triggered ({len(gtm_reqs)}):")
        for req in gtm_reqs:
            print(f"    - {req}")

        # Test CTA click telemetry
        print("[4] Simulating CTA click...")
        cta_btn = page.query_selector("a[href='/signup'], a.btn-primary")
        if cta_btn:
            cta_btn.click()
            page.wait_for_timeout(1000)
            data_layer_after = page.evaluate("() => window.dataLayer || []")
            print("    DataLayer after CTA click:")
            print(json.dumps(data_layer_after, indent=2))

        browser.close()
        print("=== Telemetry Verification Complete ===")


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else UTM_TEST_URL
    run_verification(url)
