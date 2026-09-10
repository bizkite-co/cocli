"""
Verification tests for getretirementtaxanalyzer.com SEO, GTM container & dataLayer telemetry.
"""

from __future__ import annotations

from pathlib import Path

WEBSITE_ROOT = Path("/home/mstouffer/repos/prs/getretirementtaxanalyzer.com")


def test_base_html_contains_seo_and_gtm_container() -> None:
    base_html = WEBSITE_ROOT / "src" / "_includes" / "base.html"
    assert base_html.exists()
    content = base_html.read_text(encoding="utf-8")

    # Check GTM container ID
    assert "GTM-53F6J2WX" in content, "Base HTML must contain Google Tag Manager container ID GTM-53F6J2WX"

    # Check SEO meta elements
    assert 'name="description"' in content, "Base HTML must include meta description tag"
    assert 'rel="canonical"' in content, "Base HTML must include canonical link tag"
    assert 'property="og:title"' in content, "Base HTML must include OpenGraph title tag"
    assert 'property="og:image"' in content, "Base HTML must include OpenGraph image tag"
    assert 'name="twitter:card"' in content, "Base HTML must include Twitter card tag"
    assert 'application/ld+json' in content, "Base HTML must include JSON-LD structured data"


def test_script_js_contains_datalayer_and_utm_tracking() -> None:
    script_js = WEBSITE_ROOT / "src" / "assets" / "script.js"
    assert script_js.exists()
    content = script_js.read_text(encoding="utf-8")

    assert "window.dataLayer" in content, "script.js must initialize window.dataLayer"
    assert "utm_source" in content, "script.js must parse utm_source"
    assert "utm_campaign" in content, "script.js must parse utm_campaign"
    assert "cta_click" in content, "script.js must emit cta_click telemetry events"


def test_robots_txt_and_sitemap_exist() -> None:
    robots_txt = WEBSITE_ROOT / "src" / "robots.txt"
    sitemap_xml = WEBSITE_ROOT / "src" / "sitemap.xml"

    assert robots_txt.exists(), "robots.txt must exist in src/"
    assert sitemap_xml.exists(), "sitemap.xml template must exist in src/"

    robots_content = robots_txt.read_text(encoding="utf-8")
    assert "Sitemap: https://getretirementtaxanalyzer.com/sitemap.xml" in robots_content


def test_telemetry_provider_status_check() -> None:
    from cocli.application.telemetry_service import GoogleTelemetryProvider

    provider = GoogleTelemetryProvider("roadmap")
    status = provider.check_telemetry_status()

    assert "active_account" in status
    assert "gcloud_token_valid" in status
    assert status["ga4_measurement_id"] is not None
    assert status["compiled_manifest_exists"] is True


def test_telemetry_wizard_cli_runner() -> None:
    from typer.testing import CliRunner
    from cocli.commands.telemetry import app

    runner = CliRunner()
    res = runner.invoke(app, ["wizard", "--skip-verify"])
    assert res.exit_code == 0
    assert "GTM & Web Telemetry Setup Wizard" in res.output
    assert "Phase 1: Diagnostic Status Check" in res.output
    assert "Phase 2: Compiling GTM IaC Manifest" in res.output
    assert "Phase 4: Container Quality & Completion Summary" in res.output

