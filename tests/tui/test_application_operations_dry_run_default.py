import pytest
from textual.widgets import Checkbox, ListView

from cocli.tui.app import CocliApp
from cocli.tui.widgets.application_view import ApplicationView
from conftest import wait_for_widget


async def _navigate_to_operations(driver) -> ApplicationView:
    await driver.press("space")
    await driver.pause(0.1)
    await driver.press("a")
    await driver.pause(0.1)

    application_view = await wait_for_widget(driver, ApplicationView)
    nav_list = application_view.query_one("#app_nav_list", ListView)
    nav_list.index = 5  # Operations
    nav_list.action_select_cursor()
    await driver.pause(0.2)
    return application_view


async def _highlight_operation(driver, application_view: ApplicationView, op_id: str) -> None:
    ops_list = application_view.query_one("#sidebar_operations", ListView)
    for i, item in enumerate(ops_list.children):
        if item.id == op_id:
            ops_list.index = i
            break
    else:
        raise AssertionError(f"{op_id} not found in sidebar_operations")
    await driver.pause(0.3)


@pytest.mark.asyncio
async def test_compile_to_call_dry_run_checkbox_defaults_to_checked():
    """Regression (Mark, 2026-09-01): "the app is too new to expect users
    to know what it is going to do" - the first run of an operation from
    this panel must be a preview, not a live write, until the user
    consciously unchecks Dry run."""
    app = CocliApp(auto_show=False)
    async with app.run_test() as driver:
        application_view = await _navigate_to_operations(driver)
        await _highlight_operation(driver, application_view, "op_compile_to_call")

        checkbox = application_view.query_one("#op_dry_run_checkbox", Checkbox)
        assert checkbox.value is True
        assert application_view.query_one("#op_dry_run_container").display is True


@pytest.mark.asyncio
async def test_purge_to_call_dry_run_checkbox_defaults_to_checked():
    """Regression (Mark, 2026-09-01): "Same for purge" - the destructive
    standalone purge operation gets the same preview-first safety net as
    compile_to_call, not just an immediate delete."""
    app = CocliApp(auto_show=False)
    async with app.run_test() as driver:
        application_view = await _navigate_to_operations(driver)
        await _highlight_operation(driver, application_view, "op_purge_to_call")

        checkbox = application_view.query_one("#op_dry_run_checkbox", Checkbox)
        assert checkbox.value is True
        assert application_view.query_one("#op_dry_run_container").display is True
        # Purge has no limit/purge-checkbox fields of its own.
        assert application_view.query_one("#op_limit_container").display is False
        assert application_view.query_one("#op_purge_container").display is False


@pytest.mark.asyncio
async def test_running_purge_to_call_with_default_checkbox_does_not_delete_anything():
    """The actual end-to-end safety property: leaving the default (checked)
    Dry run box and running the operation must not touch the real queue."""
    from unittest.mock import patch

    app = CocliApp(auto_show=False)
    async with app.run_test() as driver:
        application_view = await _navigate_to_operations(driver)
        await _highlight_operation(driver, application_view, "op_purge_to_call")

        with patch(
            "cocli.application.operation_service.OperationService._purge_to_call_pending_files"
        ) as mock_purge:
            worker = application_view.run_operation("op_purge_to_call")
            await worker.wait()
            await driver.pause(0.2)

        mock_purge.assert_not_called()
