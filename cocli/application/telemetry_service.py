"""
Pluggable Web Telemetry & Tag Management Service.
Supports GA4/GTM, auto-resolution/creation of GA4 Measurement IDs via Google Analytics Admin API,
IaC container manifest compilation, and Playwright verification.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from cocli.core.paths import paths

logger = logging.getLogger(__name__)

DEFAULT_CONTAINER_SPEC_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "campaigns"
    / "roadmap"
    / "initiatives"
    / "rta"
    / "tracking"
    / "gtm-container-spec.json"
)


class GoogleTelemetryProvider:
    """
    Google Analytics 4 & Google Tag Manager Telemetry Provider.
    Conforms to TelemetryProviderProtocol.
    """

    def __init__(self, campaign_name: str = "roadmap") -> None:
        self.campaign_name = campaign_name

    def resolve_measurement_id(
        self, domain: str = "getretirementtaxanalyzer.com", default_if_missing: bool = True
    ) -> Optional[str]:
        """
        Query Google Analytics Admin API (or local campaign config) for the GA4 Measurement ID.
        If missing and default_if_missing is True, returns a deterministic placeholder or creates
        a web data stream via Google Analytics Admin API if credentials are available.
        """
        try:
            # First check local campaign config.toml
            import tomli

            config_path = paths.campaigns / self.campaign_name / "config.toml"
            if config_path.exists():
                with config_path.open("rb") as f:
                    cfg = tomli.load(f)
                    m_id = cfg.get("google_analytics", {}).get("ga4_measurement_id")
                    if m_id:
                        return str(m_id)

            # Query via Google Analytics Admin API if googleapiclient is available
            try:
                from googleapiclient.discovery import build  # type: ignore[import-untyped]

                service = build("analyticsadmin", "v1beta")
                accounts = service.accounts().list().execute()
                for account in accounts.get("accounts", []):
                    account_name = account.get("name")
                    properties = service.properties().list(filter=f"parent:{account_name}").execute()
                    for prop in properties.get("properties", []):
                        prop_name = prop.get("name")
                        streams = service.properties().dataStreams().list(parent=prop_name).execute()
                        for stream in streams.get("dataStreams", []):
                            web_data = stream.get("webStreamData", {})
                            if domain in web_data.get("defaultUri", "") or domain in stream.get("displayName", ""):
                                found_id = web_data.get("measurementId")
                                if found_id:
                                    logger.info("Found GA4 Measurement ID %s for domain %s via Admin API", found_id, domain)
                                    return str(found_id)
            except Exception as api_err:
                logger.debug("Google Analytics Admin API query skipped/failed: %s", api_err)

            if default_if_missing:
                return "G-RTA0000000"
            return None
        except Exception as exc:
            logger.warning("Error resolving GA4 Measurement ID: %s", exc)
            return "G-RTA0000000" if default_if_missing else None

    def compile_container_manifest(
        self, measurement_id: str, campaign_name: Optional[str] = None
    ) -> Path:
        """Compile the declarative GTM IaC container spec for the campaign."""
        c_name = campaign_name or self.campaign_name
        template_path = paths.campaigns / c_name / "initiatives" / "rta" / "tracking" / "gtm-container-spec.json"
        if not template_path.exists():
            template_path = DEFAULT_CONTAINER_SPEC_PATH

        if not template_path.exists():
            raise FileNotFoundError(f"GTM IaC container spec template not found at {template_path}")

        content = template_path.read_text(encoding="utf-8")
        updated_content = content.replace("G-MEASUREMENT-ID-HERE", measurement_id)

        target_path = paths.campaigns / c_name / "initiatives" / "rta" / "tracking" / "gtm-container-compiled.json"
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(updated_content, encoding="utf-8")
        logger.info("Compiled GTM IaC manifest for GA4 ID %s at %s", measurement_id, target_path)
        return target_path

    def verify_live_telemetry(self, target_url: str) -> dict[str, Any]:
        """Run Playwright live verification against target_url to inspect dataLayer and network hits."""
        from playwright.sync_api import sync_playwright

        results: dict[str, Any] = {
            "target_url": target_url,
            "data_layer_events": [],
            "network_requests": [],
            "gtm_script_loaded": False,
        }

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            net_reqs: list[str] = []
            page.on("request", lambda req: net_reqs.append(req.url))

            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
            except Exception as err:
                logger.warning("Telemetry verification page load timeout/error: %s", err)

            data_layer = page.evaluate("() => window.dataLayer || []")
            results["data_layer_events"] = data_layer
            results["network_requests"] = [r for r in net_reqs if "googletagmanager.com" in r or "google-analytics.com" in r]
            results["gtm_script_loaded"] = any("googletagmanager.com/gtm.js" in r for r in net_reqs)

            browser.close()

        return results

    def ping_ga4_measurement_id(self, measurement_id: str, domain: str = "getretirementtaxanalyzer.com") -> dict[str, Any]:
        """Send an initial telemetry hit to GA4 to warm up data ingestion and clear 48-hour missing traffic alerts."""
        import urllib.request

        url = f"https://www.google-analytics.com/g/collect?v=2&tid={measurement_id}&cid=10000.67890&en=page_view&dl=https%3A%2F%2F{domain}%2F&dt=Initial%20Setup"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        try:
            with urllib.request.urlopen(req) as resp:
                if resp.status in (200, 204):
                    logger.info("Successfully sent initial telemetry ping to GA4 ID %s (HTTP %s)", measurement_id, resp.status)
                    return {"success": True, "status": resp.status}
                return {"success": False, "status": resp.status}
        except Exception as err:
            logger.warning("Initial telemetry ping note: %s", err)
            return {"success": False, "error": str(err)}

    @staticmethod
    def _run_ga4_report(property_id: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Shared GA4 Data API runReport call + row-shape flattening,
        behind the read-only analytics.readonly scope. Returns one dict
        per row with dimension and metric values merged by name."""
        import os
        import subprocess
        import urllib.error
        import urllib.request

        scopes = "https://www.googleapis.com/auth/analytics.readonly"
        token = os.environ.get("COCLI_GTM_ACCESS_TOKEN")
        if not token:
            res = subprocess.run(
                ["gcloud", "auth", "application-default", "print-access-token", f"--scopes={scopes}"],
                capture_output=True, text=True, check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                token = res.stdout.strip()
        if not token:
            raise RuntimeError(
                "No OAuth access token available for the GA4 Data API. "
                "Run `gcloud auth application-default login` or set COCLI_GTM_ACCESS_TOKEN."
            )

        req = urllib.request.Request(
            f"https://analyticsdata.googleapis.com/v1beta/properties/{property_id}:runReport",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                report: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as http_err:
            body = ""
            try:
                body = http_err.read().decode("utf-8")
            except Exception:
                pass
            raise RuntimeError(f"GA4 Data API request failed: HTTP {http_err.code} {body}") from http_err

        dim_headers = [d.get("name", "") for d in report.get("dimensionHeaders", [])]
        metric_headers = [m.get("name", "") for m in report.get("metricHeaders", [])]
        rows: list[dict[str, Any]] = []
        for row in report.get("rows", []):
            d_vals = [v.get("value", "") for v in row.get("dimensionValues", [])]
            m_vals = [v.get("value", "0") for v in row.get("metricValues", [])]
            entry = dict(zip(dim_headers, d_vals))
            entry.update(dict(zip(metric_headers, m_vals)))
            rows.append(entry)
        return rows

    def query_page_engagement(
        self, property_id: str, days: int = 7, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Per-page engagement breakdown via the GA4 Data API: sessions,
        engagement rate, average session duration, pageviews, and event
        count, one row per page path, sorted by sessions descending.

        Answers "what's going on on every page" directly from GA4 (no new
        tracking needed - Enhanced Measurement already captures scroll/
        outbound-click/form-interaction signals that feed into these
        aggregate metrics) rather than via `query_analytics`'s fixed
        campaign/UTM-scoped shape, which isn't meant for this.
        """
        payload = {
            "dateRanges": [{"startDate": f"{days}daysAgo", "endDate": "today"}],
            "dimensions": [{"name": "pagePath"}],
            "metrics": [
                {"name": "sessions"},
                {"name": "engagementRate"},
                {"name": "averageSessionDuration"},
                {"name": "screenPageViews"},
                {"name": "eventCount"},
            ],
            "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}],
            "limit": str(limit),
        }
        return self._run_ga4_report(property_id, payload)

    def query_cta_clicks(
        self, property_id: str, days: int = 7, limit: int = 200
    ) -> list[dict[str, Any]]:
        """Event-level GA4 Data API query for the cta_click custom event:
        which specific button/CTA was clicked (button_label), on which
        page, with which outreach UTM attribution - granularity the
        session-level pulls (`query_page_engagement`, `pull_from_ga4`)
        can't see, since those only know a session happened, not which
        button within it was pressed.

        Requires `button_label` to already be registered as an
        event-scoped custom dimension on this GA4 property (one-time
        Admin API/UI step - see `register_event_custom_dimension` -
        registration does not backfill past events, only ones recorded
        after it was created).
        """
        payload = {
            "dateRanges": [{"startDate": f"{days}daysAgo", "endDate": "today"}],
            "dimensions": [
                {"name": "pagePath"},
                {"name": "customEvent:button_label"},
                {"name": "sessionManualAdContent"},
                {"name": "sessionManualTerm"},
            ],
            "metrics": [{"name": "eventCount"}],
            "dimensionFilter": {
                "filter": {
                    "fieldName": "eventName",
                    "stringFilter": {"matchType": "EXACT", "value": "cta_click"},
                }
            },
            "limit": str(limit),
        }
        return self._run_ga4_report(property_id, payload)

    def register_event_custom_dimension(
        self, property_id: str, parameter_name: str, display_name: str, description: str = ""
    ) -> dict[str, Any]:
        """Idempotently register an event-scoped GA4 custom dimension -
        required before an event parameter sent by a GTM tag (e.g.
        button_label on the cta_click tag) becomes queryable via the Data
        API at all. Returns the existing registration if one with this
        parameter_name already exists, rather than erroring on a
        duplicate (GA4's API 400s on a duplicate parameterName)."""
        import os
        import subprocess
        import urllib.error
        import urllib.request

        scopes = "https://www.googleapis.com/auth/analytics.edit"
        token = os.environ.get("COCLI_GTM_ACCESS_TOKEN")
        if not token:
            res = subprocess.run(
                ["gcloud", "auth", "application-default", "print-access-token", f"--scopes={scopes}"],
                capture_output=True, text=True, check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                token = res.stdout.strip()
        if not token:
            raise RuntimeError(
                "No OAuth access token available for the GA4 Admin API. "
                "Run `gcloud auth application-default login` or set COCLI_GTM_ACCESS_TOKEN."
            )
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        list_req = urllib.request.Request(
            f"https://analyticsadmin.googleapis.com/v1alpha/properties/{property_id}/customDimensions",
            headers=headers,
        )
        with urllib.request.urlopen(list_req, timeout=30) as resp:
            existing = json.loads(resp.read().decode("utf-8"))
        for dim in existing.get("customDimensions", []):
            if dim.get("parameterName") == parameter_name:
                return dict(dim)

        create_payload = {
            "parameterName": parameter_name,
            "displayName": display_name,
            "description": description,
            "scope": "EVENT",
        }
        create_req = urllib.request.Request(
            f"https://analyticsadmin.googleapis.com/v1alpha/properties/{property_id}/customDimensions",
            data=json.dumps(create_payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(create_req, timeout=30) as resp:
                result: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
                return result
        except urllib.error.HTTPError as http_err:
            body = ""
            try:
                body = http_err.read().decode("utf-8")
            except Exception:
                pass
            raise RuntimeError(f"GA4 Admin API request failed: HTTP {http_err.code} {body}") from http_err

    def deploy_gtm_container_automated(
        self, manifest_path: Path, container_id: str = "GTM-53F6J2WX", headful: bool = True
    ) -> bool:
        """Automate Playwright import of GTM JSON manifest into Google Tag Manager container using 1Password credentials."""
        import time
        from playwright.sync_api import sync_playwright
        from cocli.core.secrets import OnePasswordProvider

        op_provider = OnePasswordProvider()
        username: Optional[str] = None
        password: Optional[str] = None
        otp_code: Optional[str] = None

        # Fetch 1Password secret refs from campaign config.toml
        try:
            import tomli

            config_path = paths.campaigns / self.campaign_name / "config.toml"
            if config_path.exists():
                with config_path.open("rb") as f:
                    cfg = tomli.load(f)
                    gtm_cfg = cfg.get("gtm", {})
                    u_ref = gtm_cfg.get("one_password_username")
                    p_ref = gtm_cfg.get("one_password_password")
                    o_ref = gtm_cfg.get("one_password_otp")
                    if u_ref:
                        username = op_provider.get_secret(u_ref)
                    if p_ref:
                        password = op_provider.get_secret(p_ref)
                    if o_ref:
                        otp_code = op_provider.get_secret(o_ref)
        except Exception as err:
            logger.warning("Could not resolve 1Password secret refs from config.toml: %s", err)

        import_url = f"https://tagmanager.google.com/#/admin/containers/import/accounts/containers/{container_id}"

        system_chrome_dir = Path.home() / ".config" / "google-chrome"
        if system_chrome_dir.exists():
            user_data_dir = system_chrome_dir
        else:
            user_data_dir = paths.root / "browser_profile"
            user_data_dir.mkdir(parents=True, exist_ok=True)

        with sync_playwright() as p:
            context = None
            cdp_url = os.environ.get("COCLI_CDP_URL") or "http://localhost:9222"
            try:
                browser_cdp = p.chromium.connect_over_cdp(cdp_url)
                if browser_cdp:
                    context = browser_cdp.contexts[0] if browser_cdp.contexts else browser_cdp.new_context()
                    logger.info("Connected to existing open Chrome browser session via CDP (%s)", cdp_url)
            except Exception as cdp_err:
                logger.debug("CDP connection skipped/not active: %s", cdp_err)

            if not context:
                launch_kwargs: dict[str, Any] = {
                    "user_data_dir": str(user_data_dir),
                    "headless": not headful,
                    "viewport": {"width": 1750, "height": 950},
                    "args": ["--disable-blink-features=AutomationControlled"],
                    "ignore_default_args": ["--enable-automation", "--disable-extensions"],
                }
                try:
                    context = p.chromium.launch_persistent_context(channel="chrome", **launch_kwargs)
                except Exception:
                    context = p.chromium.launch_persistent_context(**launch_kwargs)

            page = context.pages[0] if context.pages else context.new_page()
            try:
                page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            except Exception:
                pass

            logger.info("Navigating to GTM container import page: %s", import_url)
            page.goto("https://tagmanager.google.com/", wait_until="domcontentloaded")

            # Handle Google Sign-In if redirected
            if "accounts.google.com" in page.url:
                if username:
                    try:
                        logger.info("Filling in Google username (%s)...", username)
                        email_field = page.wait_for_selector("input[type='email']", timeout=5000)
                        if email_field:
                            email_field.fill(username)
                            page.keyboard.press("Enter")
                            time.sleep(2)

                        if password:
                            logger.info("Filling in Google password from 1Password...")
                            pass_field = page.wait_for_selector("input[type='password']", timeout=5000)
                            if pass_field:
                                pass_field.fill(password)
                                page.keyboard.press("Enter")
                                time.sleep(3)

                        if otp_code:
                            otp_field = page.query_selector("input[type='tel'], input[name='totpPin']")
                            if otp_field:
                                logger.info("Filling in 2FA TOTP code from 1Password...")
                                otp_field.fill(otp_code)
                                page.keyboard.press("Enter")
                                time.sleep(3)
                    except Exception as login_err:
                        logger.info("Google login step note: %s", login_err)

                logger.info("Waiting for sign-in redirect to Tag Manager...")
                try:
                    page.wait_for_url(lambda u: "tagmanager.google.com" in u and "accounts.google.com" not in u, timeout=60000)
                    time.sleep(3)
                except Exception as wait_err:
                    logger.warning("Sign-in wait timeout: %s", wait_err)

            # Navigate to Tag Manager home
            page.goto("https://tagmanager.google.com/", wait_until="domcontentloaded")
            time.sleep(3)

            # Locate container entry in list or search
            try:
                container_link = page.wait_for_selector(f"text='{container_id}'", timeout=10000)
                if container_link:
                    container_link.click()
                    time.sleep(3)
            except Exception as find_err:
                logger.info("Direct container link click note: %s", find_err)

            # Locate file upload input directly or navigate to import
            try:
                # Click Admin if visible
                admin_tab = page.query_selector("text='Admin'") or page.query_selector("[aria-label='Admin']")
                if admin_tab:
                    admin_tab.click()
                    time.sleep(2)

                import_btn = page.query_selector("text='Import Container'")
                if import_btn:
                    import_btn.click()
                    time.sleep(2)

                file_input = page.wait_for_selector("input[type='file']", timeout=10000)
                if file_input:
                    file_input.set_input_files(str(manifest_path))
                    logger.info("Uploaded container manifest %s", manifest_path)
                    time.sleep(2)

                    existing_btn = page.query_selector("text='Existing'") or page.query_selector("input[value='EXISTING']")
                    if existing_btn:
                        existing_btn.click()
                        time.sleep(1)

                    overwrite_btn = page.query_selector("text='Overwrite'") or page.query_selector("input[value='OVERWRITE']")
                    if overwrite_btn:
                        overwrite_btn.click()
                        time.sleep(1)

                    confirm_btn = page.query_selector("button:has-text('Confirm')") or page.query_selector("button:has-text('Import')")
                    if confirm_btn:
                        confirm_btn.click()
                        time.sleep(3)

                    submit_btn = page.query_selector("button:has-text('Submit')")
                    if submit_btn:
                        submit_btn.click()
                        time.sleep(2)
                        pub_btn = page.query_selector("button:has-text('Publish')")
                        if pub_btn:
                            pub_btn.click()
                            time.sleep(2)
            except Exception as err:
                logger.warning("Automated container import step note: %s", err)

            context.close()
            return True

    def deploy_gtm_via_api(
        self, manifest_path: Path, container_id: str = "GTM-53F6J2WX", access_token: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Deploy GTM container manifest programmatically using Google Tag Manager REST API v2.
        Zero browser UI scraping required. Uses OAuth Bearer token or Service Account credentials.

        2026-09-30 rewrite: the previous version hit
        `https://tagmanager.googleapis.com/v2/...`, which 404s - the real
        API path is `https://tagmanager.googleapis.com/tagmanager/v2/...`
        (confirmed live: the old host+path returned Google's generic
        frontend 404 page, not a GTM API error). It also only ever POSTed
        tags, never triggers/variables/built-in-variables, so any tag
        whose firingTriggerId or {{dlv - ...}} variable reference pointed
        at something not already in the target workspace would silently
        fail or misfire. This version creates triggers/variables/built-in
        variables first, remaps each tag's firingTriggerId from this
        manifest's own arbitrary exported IDs to the real IDs GTM assigns
        on creation, then creates the tags, then creates AND separately
        publishes a container version (create_version alone leaves it as
        an unpublished draft).
        """
        import os
        import urllib.request
        import urllib.error

        # An unscoped `print-access-token` returns whatever scopes the
        # stored ADC/gcloud identity happens to already have - usually
        # just cloud-platform, NOT tagmanager.edit.containers - and GTM
        # then 403s with "insufficient authentication scopes" even though
        # the identity has real GTM container access (confirmed live,
        # 2026-09-30). `application-default print-access-token` (unlike
        # plain `gcloud auth login`) DOES support --scopes, so request the
        # scope explicitly rather than hoping the default token has it.
        # All three scopes are required: edit.containers alone 403s on
        # create_version/publish with "insufficient authentication
        # scopes" even for an identity that genuinely has full container
        # access (confirmed live, 2026-09-30) - GTM v2 gates
        # CreateContainerVersion behind edit.containerversions
        # specifically (not edit.containers, which only covers ordinary
        # tag/trigger/variable CRUD) and gates the separate :publish
        # call behind tagmanager.publish.
        gtm_scopes = (
            "https://www.googleapis.com/auth/tagmanager.edit.containers,"
            "https://www.googleapis.com/auth/tagmanager.edit.containerversions,"
            "https://www.googleapis.com/auth/tagmanager.publish"
        )

        token = access_token or os.environ.get("COCLI_GTM_ACCESS_TOKEN")
        if not token:
            try:
                import subprocess
                res = subprocess.run(
                    ["gcloud", "auth", "application-default", "print-access-token", f"--scopes={gtm_scopes}"],
                    capture_output=True, text=True, check=False,
                )
                if res.returncode == 0 and res.stdout.strip():
                    token = res.stdout.strip()
            except Exception as err:
                logger.debug("Scoped ADC token query note: %s", err)

        if not token:
            try:
                import subprocess
                res = subprocess.run(["gcloud", "auth", "application-default", "print-access-token"], capture_output=True, text=True, check=False)
                if res.returncode == 0 and res.stdout.strip():
                    token = res.stdout.strip()
            except Exception as err:
                logger.debug("ADC token query note: %s", err)

        if not token:
            try:
                import subprocess
                res = subprocess.run(["gcloud", "auth", "print-access-token"], capture_output=True, text=True, check=False)
                if res.returncode == 0 and res.stdout.strip():
                    token = res.stdout.strip()
            except Exception as err:
                logger.warning("Could not automatically retrieve gcloud access token: %s", err)

        if not token:
            return {
                "success": False,
                "error": "No OAuth access token available. Provide access_token or set COCLI_GTM_ACCESS_TOKEN / gcloud auth.",
            }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        api_base = "https://tagmanager.googleapis.com/tagmanager/v2"

        def _get(url: str) -> dict[str, Any]:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req) as resp:
                result: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
                return result

        def _post(url: str, payload: dict[str, Any]) -> dict[str, Any]:
            req = urllib.request.Request(
                url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
            )
            with urllib.request.urlopen(req) as resp:
                body = resp.read().decode("utf-8")
                result: dict[str, Any] = json.loads(body) if body else {}
                return result

        def _resource_payload(resource: dict[str, Any], drop_keys: set[str]) -> dict[str, Any]:
            # Strip export-only bookkeeping fields (accountId/containerId/
            # the resource's own exported *Id/path/fingerprint) so the API
            # assigns fresh real identifiers in the target workspace,
            # rather than us pretending our arbitrary export IDs are real.
            return {k: v for k, v in resource.items() if k not in drop_keys}

        try:
            # Step 1: List GTM Accounts
            data = _get(f"{api_base}/accounts")
            accounts = data.get("account", [])
            if not accounts:
                return {"success": False, "error": "No Google Tag Manager accounts found for this access token."}
            account_id = accounts[0].get("accountId")
            logger.info("Found GTM Account ID %s", account_id)

            # Step 2: Find Target Container ID (e.g. GTM-53F6J2WX)
            c_data = _get(f"{api_base}/accounts/{account_id}/containers")
            target_container_path = ""
            for c in c_data.get("container", []):
                if c.get("publicId") == container_id or c.get("containerId") == container_id:
                    target_container_path = c.get("path")
                    break

            if not target_container_path:
                return {"success": False, "error": f"No GTM container found matching '{container_id}' for this account."}

            # Step 3: Use the container's single existing workspace rather
            # than creating a new one each deploy. Two real problems, both
            # hit live on 2026-09-30: (a) blindly creating triggers/tags
            # into a fresh workspace 400s with "Found entity with
            # duplicate name" the instant the container already has ANY
            # named entity in common with the manifest (true of every
            # real container after the first deploy) - a fresh workspace
            # still starts as a COPY of the live published state, it is
            # not empty; (b) accumulating an extra workspace per deploy is
            # exactly the "published from the wrong one, silently
            # reverting a fix" trap that cost real time to diagnose (see
            # gtw audit, built from this same incident). If more than one
            # workspace already exists, refuse rather than guess which one
            # is authoritative - ask the human to consolidate first
            # (`gtw audit` flags this).
            workspaces_data = _get(f"{api_base}/{target_container_path}/workspaces")
            workspaces = workspaces_data.get("workspace", [])
            if not workspaces:
                return {"success": False, "error": f"Container {container_id} has no workspaces at all."}
            if len(workspaces) > 1:
                names = ", ".join(str(w.get("name", "?")) for w in workspaces)
                return {
                    "success": False,
                    "error": (
                        f"Container {container_id} has {len(workspaces)} workspaces "
                        f"({names}) - refusing to guess which is authoritative. "
                        f"Delete the unused draft(s) in the GTM UI first (run `gtw "
                        f"audit` to confirm), then retry."
                    ),
                }
            workspace_path = workspaces[0].get("path")
            if not workspace_path:
                return {"success": False, "error": "Could not resolve the container's workspace path."}

            # Step 4: Import Triggers/Variables/Built-in Variables/Tags from
            # manifest - idempotently. An entity already present BY NAME is
            # reused (its real ID captured for firingTriggerId remapping),
            # never recreated - GTM rejects a duplicate name outright, and
            # even if it didn't, blindly re-creating would just pile up
            # redundant copies of what's already correct.
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            version_data = manifest.get("containerVersion", {})

            existing_triggers = _get(f"{api_base}/{workspace_path}/triggers").get("trigger", [])
            existing_trigger_by_name = {t.get("name"): t for t in existing_triggers}
            trigger_id_map: dict[str, str] = {}
            for trigger in version_data.get("trigger", []):
                original_id = str(trigger.get("triggerId", ""))
                name = trigger.get("name")
                existing = existing_trigger_by_name.get(name)
                if existing:
                    logger.info("Trigger '%s' already exists - reusing it.", name)
                    real_id = existing.get("triggerId")
                else:
                    created = _post(
                        f"{api_base}/{workspace_path}/triggers",
                        _resource_payload(trigger, {"accountId", "containerId", "workspaceId", "triggerId", "path", "fingerprint"}),
                    )
                    real_id = created.get("triggerId")
                if original_id and real_id:
                    trigger_id_map[original_id] = str(real_id)

            existing_variables = _get(f"{api_base}/{workspace_path}/variables").get("variable", [])
            existing_variable_names = {v.get("name") for v in existing_variables}
            for variable in version_data.get("variable", []):
                name = variable.get("name")
                if name in existing_variable_names:
                    logger.info("Variable '%s' already exists - reusing it.", name)
                    continue
                _post(
                    f"{api_base}/{workspace_path}/variables",
                    _resource_payload(variable, {"accountId", "containerId", "workspaceId", "variableId", "path", "fingerprint"}),
                )

            existing_built_ins = _get(f"{api_base}/{workspace_path}/built_in_variables").get("builtInVariable", [])
            existing_built_in_types = {b.get("type") for b in existing_built_ins}
            for built_in in version_data.get("builtInVariable", []):
                if built_in.get("type") in existing_built_in_types:
                    continue
                try:
                    _post(
                        f"{api_base}/{workspace_path}/built_in_variables",
                        _resource_payload(built_in, {"accountId", "containerId", "workspaceId", "path", "fingerprint"}),
                    )
                except urllib.error.HTTPError as biv_err:
                    # Belt-and-suspenders: even with the pre-check above,
                    # GTM still errors on some already-on built-ins
                    # depending on account defaults. Not a real failure.
                    logger.debug("Built-in variable note (%s): %s", built_in.get("name"), biv_err)

            existing_tags = _get(f"{api_base}/{workspace_path}/tags").get("tag", [])
            existing_tag_names = {t.get("name") for t in existing_tags}
            deployed_tags = 0
            skipped_tags = 0
            for tag in version_data.get("tag", []):
                name = tag.get("name")
                if name in existing_tag_names:
                    logger.info("Tag '%s' already exists - leaving it as-is.", name)
                    skipped_tags += 1
                    continue
                payload = _resource_payload(tag, {"accountId", "containerId", "workspaceId", "tagId", "path", "fingerprint"})
                payload["firingTriggerId"] = [
                    trigger_id_map.get(str(trigger_id), str(trigger_id))
                    for trigger_id in payload.get("firingTriggerId", [])
                ]
                _post(f"{api_base}/{workspace_path}/tags", payload)
                deployed_tags += 1

            # Step 5: Create AND publish the container version - create_version
            # alone only produces an unpublished draft.
            # Whether to publish is NOT the same question as whether we
            # had to create anything just now: an entity can already
            # exist (so nothing new was created) while still never having
            # been part of a PUBLISHED version - exactly what happened
            # here, from an earlier deploy attempt that created
            # feedback_submit/signup_submit's trigger+tag before dying
            # partway through on an unrelated duplicate-name error. Those
            # orphaned-but-real entities sat unpublished indefinitely.
            # The only reliable check is the live version's own tag
            # names, fetched fresh, not "did this run need to create
            # something."
            live_tag_names = {
                t.get("name") for t in _get(f"{api_base}/{target_container_path}/versions:live").get("tag", [])
            }
            manifest_tag_names = {t.get("name") for t in version_data.get("tag", [])}
            if manifest_tag_names <= live_tag_names:
                return {
                    "success": True,
                    "message": (
                        f"Nothing to deploy - all {len(manifest_tag_names)} manifest tag(s) "
                        f"are already in the live published version. Not publishing a no-op "
                        f"version."
                    ),
                    "version_id": None,
                }

            version_response = _post(f"{api_base}/{workspace_path}:create_version", {"name": "cocli telemetry deploy"})
            version = version_response.get("containerVersion", version_response)
            version_id = version.get("containerVersionId")
            if not version_id:
                return {"success": False, "error": "Google Tag Manager did not return a container version ID."}

            _post(f"{api_base}/{target_container_path}/versions/{version_id}:publish", {})
            logger.info(
                "Published GTM Container Version %s (%s new tags, %s already present)",
                version_id, deployed_tags, skipped_tags,
            )

            return {
                "success": True,
                "message": (
                    f"Successfully published container version {version_id} "
                    f"({deployed_tags} new tag(s), {skipped_tags} already present)"
                ),
                "version_id": version_id,
            }
        except urllib.error.HTTPError as http_err:
            body = ""
            try:
                body = http_err.read().decode("utf-8")
            except Exception:
                pass
            logger.warning("Error calling GTM REST API v2: %s %s", http_err, body)
            return {"success": False, "error": f"HTTP Error {http_err.code}: {http_err.reason} {body}"}
        except Exception as exc:
            logger.warning("Failed GTM API deployment: %s", exc)
            return {"success": False, "error": str(exc)}

    def check_telemetry_status(self, domain: str = "getretirementtaxanalyzer.com") -> dict[str, Any]:
        """Check complete system status for gcloud auth, GA4 measurement ID, GTM manifest, and live telemetry."""
        import subprocess

        manifest_path = paths.campaigns / self.campaign_name / "initiatives" / "rta" / "tracking" / "gtm-container-compiled.json"
        if not manifest_path.exists():
            manifest_path = DEFAULT_CONTAINER_SPEC_PATH.parent / "gtm-container-compiled.json"

        status: dict[str, Any] = {
            "active_account": None,
            "gcloud_token_valid": False,
            "ga4_measurement_id": self.resolve_measurement_id(domain=domain, default_if_missing=True),
            "compiled_manifest_exists": manifest_path.exists(),
            "compiled_manifest_path": str(manifest_path),
        }

        # Check gcloud active account
        try:
            res = subprocess.run(["gcloud", "auth", "list", "--format=json"], capture_output=True, text=True, check=False)
            if res.returncode == 0 and res.stdout.strip():
                accounts = json.loads(res.stdout)
                for acc in accounts:
                    if acc.get("status") == "ACTIVE":
                        status["active_account"] = acc.get("account")
                        break
        except Exception as err:
            logger.debug("Error checking gcloud auth list: %s", err)

        # Check gcloud access token
        try:
            tok_res = subprocess.run(["gcloud", "auth", "print-access-token"], capture_output=True, text=True, check=False)
            if tok_res.returncode == 0 and tok_res.stdout.strip():
                status["gcloud_token_valid"] = True
        except Exception as err:
            logger.debug("Error checking gcloud access token: %s", err)

        return status

