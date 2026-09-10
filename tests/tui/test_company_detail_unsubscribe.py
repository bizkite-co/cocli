from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cocli.core.paths import paths
from cocli.tui.app import CocliApp
from cocli.tui.widgets.company_detail import CompanyDetail
from cocli.core.exclusions import ExclusionManager


@pytest.fixture
def mock_company_data(tmp_path: Path):
    company_dir = tmp_path / "companies" / "test-co"
    notes_dir = company_dir / "notes"
    enrichments_dir = company_dir / "enrichments"
    notes_dir.mkdir(parents=True, exist_ok=True)
    enrichments_dir.mkdir(parents=True, exist_ok=True)

    return {
        "company": {
            "name": "Test Co",
            "slug": "test-co",
            "email": "owner@test.com",
            "domain": "test.com",
            "phone_1": "5551234567",
        },
        "contacts": [],
        "meetings": [],
        "notes": [],
        "website_data": None,
        "tags": [],
        "enrichment_path": str(enrichments_dir / "website.md"),
    }


async def _mount(app: CocliApp, pilot, company_data) -> CompanyDetail:
    detail = CompanyDetail(company_data)
    await app.query_one("#app_content").mount(detail)
    await pilot.pause()
    return detail


@pytest.mark.asyncio
async def test_unsubscribe_company_confirmed(mock_company_data, tmp_path):
    with patch.object(paths, "root", tmp_path):
        app = CocliApp(auto_show=False)
        async with app.run_test() as pilot:
            await _mount(app, pilot, mock_company_data)

            mock_ses = MagicMock()
            mock_ses.suppress_email.return_value = True

            with patch(
                "cocli.application.ses_suppression_service.SesSuppressionService",
                return_value=mock_ses,
            ), patch("cocli.core.config.get_campaign", return_value="turboship"):
                await pilot.press("U")
                await pilot.pause()
                await pilot.press("y")
                await pilot.pause()

        # Check local exclusion within patched paths scope
        ex_mgr = ExclusionManager("turboship")
        assert ex_mgr.is_excluded(domain="owner@test.com", slug="test-co")

        # Check SES suppression call
        mock_ses.suppress_email.assert_called_once_with("owner@test.com", reason="COMPLAINT")

        # Check UNSUBSCRIBED note file written
        notes_dir = tmp_path / "companies" / "test-co" / "notes"
        note_files = list(notes_dir.glob("*.md"))
        assert len(note_files) == 1
        content = note_files[0].read_text()
        assert "title: UNSUBSCRIBED" in content
        assert "tui_phone_unsubscribe" in content


@pytest.mark.asyncio
async def test_unsubscribe_company_cancelled(mock_company_data, tmp_path):
    with patch.object(paths, "root", tmp_path):
        app = CocliApp(auto_show=False)
        async with app.run_test() as pilot:
            await _mount(app, pilot, mock_company_data)

            mock_ses = MagicMock()

            with patch(
                "cocli.application.ses_suppression_service.SesSuppressionService",
                return_value=mock_ses,
            ), patch("cocli.core.config.get_campaign", return_value="turboship"):
                await pilot.press("U")
                await pilot.pause()
                await pilot.press("n")
                await pilot.pause()

        # Check no exclusion added within patched paths scope
        ex_mgr = ExclusionManager("turboship")
        assert not ex_mgr.is_excluded(domain="owner@test.com", slug="test-co")

        # Check SES suppression was not called
        mock_ses.suppress_email.assert_not_called()

        # Check no note file written
        notes_dir = tmp_path / "companies" / "test-co" / "notes"
        note_files = list(notes_dir.glob("*.md"))
        assert len(note_files) == 0
