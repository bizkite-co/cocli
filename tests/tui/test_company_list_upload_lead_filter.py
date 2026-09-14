"""CompanyList's `u` binding: publish lead-filter exports to the web
dashboard without regenerating them (conversation 2026-09-14)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cocli.tui.app import CocliApp
from cocli.tui.widgets.company_list import CompanyList


@pytest.mark.asyncio
async def test_upload_lead_filter_notifies_and_uploads() -> None:
    # get_campaign/WebService/get_boto3_session are local imports inside
    # the method, so patch the modules they actually come from.
    with patch("cocli.core.config.get_campaign", return_value="turboship"):
        mock_service = MagicMock()
        mock_service.resolve_deployment_config.return_value = {
            "profile": "bizkite-support",
            "bucket_name": "cocli-web-assets-example-com",
        }
        mock_service.upload_lead_filter_exports.return_value = [
            "exports/turboship-leadfilter-in.csv",
            "exports/turboship-leadfilter-out.csv",
        ]
        mock_session = MagicMock()

        app = CocliApp(auto_show=False)
        async with app.run_test():
            widget = CompanyList()
            await app.query_one("#app_content").mount(widget)

            with patch(
                "cocli.application.web_service.WebService", return_value=mock_service
            ), patch(
                "cocli.core.reporting.get_boto3_session", return_value=mock_session
            ), patch.object(
                widget.app, "notify"
            ) as mock_notify:
                await widget.action_upload_lead_filter()

        mock_service.upload_lead_filter_exports.assert_called_once_with(
            mock_session.client.return_value, "cocli-web-assets-example-com"
        )
        messages = [call.args[0] for call in mock_notify.call_args_list]
        assert any("Uploading" in m for m in messages)
        assert any("Uploaded 2" in m for m in messages)


@pytest.mark.asyncio
async def test_upload_lead_filter_reports_nothing_generated() -> None:
    with patch("cocli.core.config.get_campaign", return_value="turboship"):
        mock_service = MagicMock()
        mock_service.resolve_deployment_config.return_value = {
            "profile": "bizkite-support",
            "bucket_name": "cocli-web-assets-example-com",
        }
        mock_service.upload_lead_filter_exports.return_value = []

        app = CocliApp(auto_show=False)
        async with app.run_test():
            widget = CompanyList()
            await app.query_one("#app_content").mount(widget)

            with patch(
                "cocli.application.web_service.WebService", return_value=mock_service
            ), patch(
                "cocli.core.reporting.get_boto3_session", return_value=MagicMock()
            ), patch.object(
                widget.app, "notify"
            ) as mock_notify:
                await widget.action_upload_lead_filter()

        warning_calls = [
            call for call in mock_notify.call_args_list
            if call.kwargs.get("severity") == "warning"
        ]
        assert len(warning_calls) == 1
        assert "run the lead-filter script first" in warning_calls[0].args[0]


@pytest.mark.asyncio
async def test_upload_lead_filter_requires_a_campaign() -> None:
    with patch("cocli.core.config.get_campaign", return_value=None):
        app = CocliApp(auto_show=False)
        async with app.run_test():
            widget = CompanyList()
            await app.query_one("#app_content").mount(widget)

            with patch.object(widget.app, "notify") as mock_notify:
                await widget.action_upload_lead_filter()

        mock_notify.assert_called_once()
        assert mock_notify.call_args.kwargs.get("severity") == "error"
