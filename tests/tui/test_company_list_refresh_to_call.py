"""CompanyList's `r` binding: top up the To-Call queue by a configurable
batch size (purge always off - see get_to_call_batch_size), right from
the To-Call view, without leaving for Admin's Operations screen."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cocli.tui.app import CocliApp
from cocli.tui.widgets.company_list import CompanyList


@pytest.mark.asyncio
async def test_refresh_to_call_only_available_in_to_call_view() -> None:
    app = CocliApp(auto_show=False)
    async with app.run_test():
        widget = CompanyList()
        await app.query_one("#app_content").mount(widget)
        widget.current_filters = {}

        with patch.object(widget.app, "notify") as mock_notify, patch.object(
            widget.app, "run_worker"
        ) as mock_run_worker:
            widget.action_refresh_to_call()

        mock_notify.assert_called_once()
        assert mock_notify.call_args.kwargs.get("severity") == "warning"
        mock_run_worker.assert_not_called()


@pytest.mark.asyncio
async def test_refresh_to_call_requires_a_campaign() -> None:
    app = CocliApp(auto_show=False)
    async with app.run_test():
        widget = CompanyList()
        await app.query_one("#app_content").mount(widget)
        widget.current_filters = {"to_call": True}

        with patch("cocli.core.config.get_campaign", return_value=None), patch.object(
            widget.app, "notify"
        ) as mock_notify:
            widget.action_refresh_to_call()

        mock_notify.assert_called_once()
        assert mock_notify.call_args.kwargs.get("severity") == "error"


@pytest.mark.asyncio
async def test_refresh_to_call_runs_with_configured_batch_size_purge_off() -> None:
    app = CocliApp(auto_show=False)
    async with app.run_test():
        widget = CompanyList()
        await app.query_one("#app_content").mount(widget)

        mock_execute = AsyncMock(
            return_value={"created_count": 5, "skipped_already_pending": 2}
        )
        widget.app.services.operation_service = MagicMock(execute=mock_execute)

        with patch(
            "cocli.core.config.get_to_call_batch_size", return_value=15
        ), patch.object(widget.app, "notify") as mock_notify, patch.object(
            widget, "run_search"
        ) as mock_run_search:
            await widget._refresh_to_call("roadmap")

        mock_execute.assert_called_once_with(
            "op_compile_to_call",
            params={"purge": False, "limit": 15, "dry_run": False},
        )
        messages = [call.args[0] for call in mock_notify.call_args_list]
        assert any("up to 15" in m for m in messages)
        assert any("Added 5 lead(s) to To-Call (2 already pending)" in m for m in messages)
        mock_run_search.assert_called_once_with("")


@pytest.mark.asyncio
async def test_refresh_to_call_reports_operation_failure() -> None:
    app = CocliApp(auto_show=False)
    async with app.run_test():
        widget = CompanyList()
        await app.query_one("#app_content").mount(widget)

        mock_execute = AsyncMock(side_effect=RuntimeError("boom"))
        widget.app.services.operation_service = MagicMock(execute=mock_execute)

        with patch(
            "cocli.core.config.get_to_call_batch_size", return_value=20
        ), patch.object(widget.app, "notify") as mock_notify:
            await widget._refresh_to_call("roadmap")

        error_calls = [
            call for call in mock_notify.call_args_list
            if call.kwargs.get("severity") == "error"
        ]
        assert len(error_calls) == 1
        assert "Refresh failed" in error_calls[0].args[0]
