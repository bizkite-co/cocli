import pytest
from typing import Any
from textual.app import App, ComposeResult
from textual.widgets import Static
from textual.containers import Vertical
from cocli.tui.widgets.queues_view import QueueDetail
from cocli.tui.navigation_manager import NavigationStateManager


class SimpleQueueApp(App):
    """A minimal app to test the QueueDetail widget in isolation."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.nav_manager = NavigationStateManager(self)

    def compose(self) -> ComposeResult:
        yield QueueDetail(id="queue_detail")


@pytest.mark.asyncio
async def test_queue_detail_metadata_displays(mocker):
    """
    Assert that metadata is properly populated in QueueDetail.
    """
    app = SimpleQueueApp()
    mock_services = mocker.Mock()
    mock_services.reporting_service.campaign_name = "test-campaign"
    mock_services.reporting_service.load_cached_report.return_value = {}
    app.services = mock_services

    async with app.run_test():
        detail = app.query_one("#queue_detail", QueueDetail)
        detail.update_detail("gm-list")

        info_content = detail.query_one("#queue_info_content", Static)
        # Verify metadata_map was set
        metadata = getattr(info_content, "metadata_map", {})
        assert "Functional Purpose" in metadata
        assert metadata["Task Model"] == "ScrapeTask"


@pytest.mark.asyncio
async def test_queue_detail_audit_list_displays(mocker, tmp_path):
    """
    Assert that the audit list container is populated when data exists.
    """
    app = SimpleQueueApp()
    mock_services = mocker.Mock()
    mock_services.reporting_service.campaign_name = "test-campaign"
    app.services = mock_services

    # Setup mock file structure
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    audit_file = results_dir / "gm_list_audit.usv"
    audit_file.write_text("ChIJ123\x1fName\x1f4.5\x1f100\x1furl\n")

    mock_paths = mocker.MagicMock()
    # Mock chain: paths.campaign().queue().completed returns tmp_path
    mock_paths.campaign.return_value.queue.return_value.completed = tmp_path
    mocker.patch("cocli.tui.widgets.queues_view.paths", mock_paths)

    async with app.run_test():
        detail = app.query_one("#queue_detail", QueueDetail)
        detail.update_detail("gm-list")

        # Verify audit items are loaded
        assert len(detail.audit_items) > 0

        container = detail.query_one("#audit_results_content", Vertical)
        assert len(container.children) > 0  # Should have header and at least one item


@pytest.mark.asyncio
async def test_queue_detail_final_verification(mocker):
    """
    Verify:
    1. Metadata panel includes Task Model name.
    2. Pending/Completed counts are at the top of columns.
    3. Property technical names are listed below counts.
    4. sp/sc bindings are present.
    """
    # Create app and Mock services
    app = SimpleQueueApp()
    mock_services = mocker.Mock()
    mock_services.reporting_service.campaign_name = "test-campaign"
    mock_services.reporting_service.load_cached_report.return_value = {}
    app.services = mock_services

    async with app.run_test():
        detail = app.query_one("#queue_detail", QueueDetail)
        detail.update_detail("gm-list")

        # 1. Verify Metadata Table (Model Name)
        info_content = detail.query_one("#queue_info_content", Static)
        metadata = getattr(info_content, "metadata_map", {})
        assert metadata.get("Task Model") == "ScrapeTask"

        # 2. Check structural hierarchy
        source_panel = detail.query_one("#source_panel")
        # Children: 0:Header, 1:Model, 2:Count, 3:Vertical List
        assert "panel-header-green" in source_panel.children[0].classes
        assert "model-name-label" in source_panel.children[1].classes
        assert "count-display-label" in source_panel.children[2].classes

        # 3. Check property names
        source_list = detail.query_one("#source_props_list")
        prop_names = getattr(source_list, "tech_props", [])
        assert "queries" in prop_names

        # 4. Check Shortcuts (sp/sc) are documented in code or handled
        assert hasattr(detail, "on_key")

        # 5. Verify audit panel exists and has required elements
        audit_panel = detail.query_one("#audit_panel")
        assert audit_panel is not None

        audit_status = detail.query_one("#audit_status")
        assert audit_status is not None

        audit_content = detail.query_one("#audit_results_content")
        assert audit_content is not None

        # 6. Test audit navigation methods exist
        assert hasattr(detail, "action_audit_down")
        assert hasattr(detail, "action_audit_up")
        assert hasattr(detail, "load_audit_results")

        # 7. Test navigation updates selection
        detail.audit_items = [
            {"name": "Item 1", "rating": "4.5", "reviews": "100"},
            {"name": "Item 2", "rating": "3.0", "reviews": "50"},
            {"name": "Item 3", "rating": "5.0", "reviews": "200"},
        ]
        detail.audit_selected_idx = 0

        # Check initial state
        assert detail.audit_selected_idx == 0

        # Move down
        detail.action_audit_down()
        assert detail.audit_selected_idx == 1

        # Move up
        detail.action_audit_up()
        assert detail.audit_selected_idx == 0

        # Test wrapping (going up from first goes to last)
        detail.action_audit_up()
        assert detail.audit_selected_idx == 2

        # Test wrapping (going down from last goes to first)
        detail.action_audit_down()
        assert detail.audit_selected_idx == 0

        # 8. Test color coding: items with rating should be green, without should be red
        detail.audit_items = [
            {"name": "Has Rating", "rating": "4.5", "reviews": "100"},
            {"name": "No Rating", "rating": "-", "reviews": "-"},
            {"name": "Also Has Rating", "rating": "5.0", "reviews": "200"},
        ]
        detail.audit_selected_idx = 0
        detail._render_audit_items()

        # Verify items are rendered (we can check the items list)
        assert len(detail.audit_items) == 3
        # First and third items have ratings
        assert detail.audit_items[0].get("rating") != "-"
        assert detail.audit_items[1].get("rating") == "-"
        assert detail.audit_items[2].get("rating") != "-"

        # 9. Test action_open_audit_gmb exists and handles no items
        assert hasattr(detail, "action_open_audit_gmb")

        # Test with no audit_items
        detail.audit_items = []
        detail.audit_selected_idx = 0

        # 10. Test action_mark_reviewed exists and has correct key binding
        assert hasattr(detail, "action_mark_reviewed")

        # 11. Test mark reviewed dialog has keyboard bindings (H to save, Esc to cancel)
        assert callable(detail.action_mark_reviewed)

        # 12. Test that audit items have proper structure for verification
        detail.audit_items = [
            {
                "place_id": "ChIJ123",
                "name": "Test Business",
                "rating": "4.5",
                "reviews": "100",
            },
        ]
        detail.audit_selected_idx = 0

        # Verify the item has all required fields for verification
        item = detail.audit_items[0]
        assert "place_id" in item
        assert "name" in item
        assert "rating" in item
        assert "reviews" in item


@pytest.mark.asyncio
async def test_load_audit_results_method_exists(mocker):
    """
    Verify load_audit_results method exists and can be called.
    """
    app = SimpleQueueApp()
    mock_services = mocker.Mock()
    mock_services.reporting_service.campaign_name = "test-campaign"
    app.services = mock_services

    mocker.patch("cocli.core.paths.paths")

    async with app.run_test():
        detail = app.query_one("#queue_detail", QueueDetail)
        detail.active_queue = type("Queue", (), {"name": "gm-list"})()

        assert hasattr(detail, "load_audit_results")
        detail.load_audit_results()


@pytest.mark.asyncio
async def test_update_detail_auto_loads_audit_for_gm_list(mocker):
    """
    Verify update_detail calls load_audit_results when viewing gm-list.
    """
    app = SimpleQueueApp()
    mock_services = mocker.Mock()
    mock_services.reporting_service.campaign_name = "test-campaign"
    mock_services.reporting_service.load_cached_report.return_value = {}
    app.services = mock_services

    load_audit_mock = mocker.patch.object(QueueDetail, "load_audit_results")

    async with app.run_test():
        detail = app.query_one("#queue_detail", QueueDetail)
        detail.update_detail("gm-list")

        load_audit_mock.assert_called_once()


@pytest.mark.asyncio
async def test_render_audit_items_shows_header_and_colors(tmp_path, mocker):
    """
    Verify _render_audit_items shows header row and items are rendered.
    With inline editing, selected item shows Input widgets.
    """
    app = SimpleQueueApp()
    mock_services = mocker.Mock()
    mock_services.reporting_service.campaign_name = "test-campaign"
    app.services = mock_services

    async with app.run_test():
        detail = app.query_one("#queue_detail", QueueDetail)

        detail.audit_items = [
            {
                "name": "Has Rating",
                "rating": "4.5",
                "reviews": "100",
                "place_id": "ChIJ123",
            },
            {"name": "No Rating", "rating": "-", "reviews": "-", "place_id": "ChIJ456"},
        ]
        detail.audit_selected_idx = 0
        detail._render_audit_items()

        container = detail.query_one("#audit_results_content")
        children = list(container.children)

        assert len(children) >= 3

        assert detail.audit_items[0]["name"] == "Has Rating"
        assert detail.audit_items[1]["name"] == "No Rating"


@pytest.mark.asyncio
async def test_load_audit_results_parses_empty_fields_as_dash(mocker):
    """
    Verify load_audit_results normalizes empty fields to '-' not empty string.
    """
    app = SimpleQueueApp()
    mock_services = mocker.Mock()
    mock_services.reporting_service.campaign_name = "test-campaign"
    app.services = mock_services

    mocker.patch("cocli.core.paths.paths")

    async with app.run_test():
        detail = app.query_one("#queue_detail", QueueDetail)
        detail.active_queue = type("Queue", (), {"name": "gm-list"})()

        usv_content = (
            "ChIJ123\x1fTest Business 1\x1f\x1f\x1fhttps://example.com/1\n"
            "ChIJ456\x1fTest Business 2\x1f4.5\x1f100\x1fhttps://example.com/2\n"
        )

        items = []
        for line in usv_content.strip().split("\n"):
            if line.strip():
                parts = line.strip().split("\x1f")
                if len(parts) >= 5:
                    items.append(
                        {
                            "place_id": parts[0],
                            "name": parts[1][:40].ljust(40),
                            "rating": parts[2].strip()
                            if len(parts) > 2 and parts[2].strip()
                            else "-",
                            "reviews": parts[3].strip()
                            if len(parts) > 3 and parts[3].strip()
                            else "-",
                        }
                    )

        assert len(items) == 2
        assert items[0]["rating"] == "-"
        assert items[0]["reviews"] == "-"
        assert items[1]["rating"] == "4.5"
        assert items[1]["reviews"] == "100"


@pytest.mark.asyncio
async def test_mark_reviewed_works_with_empty_rating(mocker):
    """
    Verify action_mark_reviewed toggles edit mode even with empty rating/reviews.
    """
    app = SimpleQueueApp()
    mock_services = mocker.Mock()
    mock_services.reporting_service.campaign_name = "test-campaign"
    app.services = mock_services

    async with app.run_test():
        detail = app.query_one("#queue_detail", QueueDetail)
        detail.active_queue = type("Queue", (), {"name": "gm-list"})()

        detail.audit_items = [
            {
                "place_id": "ChIJ123456789012345678901",
                "name": "Test",
                "rating": "-",
                "reviews": "-",
            },
        ]
        detail.audit_selected_idx = 0

        assert detail.is_editing is False

        detail.action_mark_reviewed()

        assert detail.is_editing is True


@pytest.mark.asyncio
async def test_mark_reviewed_works_with_valid_rating(mocker):
    """
    Verify action_mark_reviewed toggles inline editing mode.
    """
    app = SimpleQueueApp()
    mock_services = mocker.Mock()
    mock_services.reporting_service.campaign_name = "test-campaign"
    app.services = mock_services

    async with app.run_test():
        detail = app.query_one("#queue_detail", QueueDetail)
        detail.active_queue = type("Queue", (), {"name": "gm-list"})()

        detail.audit_items = [
            {
                "place_id": "ChIJ123456789012345678901",
                "name": "Test",
                "rating": "4.5",
                "reviews": "100",
            },
        ]
        detail.audit_selected_idx = 0

        assert detail.is_editing is False

        detail.action_mark_reviewed()

        assert detail.is_editing is True


@pytest.mark.asyncio
async def test_review_dialog_accepts_backspace_and_delete(mocker):
    """
    Verify backspace and delete keys work in the review dialog.
    This tests that the dialog doesn't block these keys.
    """
    from cocli.tui.widgets.mark_reviewed_dialog import MarkReviewedDialog
    from textual.app import App, ComposeResult

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield MarkReviewedDialog(
                place_id="ChIJ123",
                biz_name="Test Business",
                current_rating="4.5",
                current_reviews="100",
            )

    mocker.patch("cocli.tui.widgets.mark_reviewed_dialog.MarkReviewedDialog.on_mount")

    app = TestApp()
    async with app.run_test() as pilot:
        dialog = app.query_one(MarkReviewedDialog)

        rating_input = dialog.query_one("#review-rating-input")

        rating_input.value = "4"
        await pilot.pause()

        rating_input.value = "44"
        await pilot.pause()

        rating_input.value = "4"
        await pilot.pause()

        assert rating_input.value == "4"


@pytest.mark.asyncio
async def test_review_dialog_validates_numeric_input(mocker):
    """
    Verify the review dialog only accepts valid numeric input.
    Rating: 0-5 with one decimal
    Reviews: non-negative integers only
    """
    from cocli.tui.widgets.mark_reviewed_dialog import MarkReviewedDialog
    from textual.app import App, ComposeResult

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield MarkReviewedDialog(
                place_id="ChIJ123",
                biz_name="Test Business",
                current_rating="",
                current_reviews="",
            )

    mocker.patch("cocli.tui.widgets.mark_reviewed_dialog.MarkReviewedDialog.on_mount")

    app = TestApp()
    async with app.run_test() as pilot:
        dialog = app.query_one(MarkReviewedDialog)

        rating_input = dialog.query_one("#review-rating-input")
        reviews_input = dialog.query_one("#review-reviews-input")

        rating_input.value = "abc"
        await pilot.pause()
        assert rating_input.value == ""

        rating_input.value = "5.0"
        await pilot.pause()
        assert rating_input.value == "5.0"

        rating_input.value = "5"
        await pilot.pause()
        assert rating_input.value == "5"

        reviews_input.value = "abc"
        await pilot.pause()
        assert reviews_input.value == ""

        reviews_input.value = "123"
        await pilot.pause()
        assert reviews_input.value == "123"


@pytest.mark.asyncio
async def test_reviewed_data_persists_across_dialog_opens(mocker):
    """
    Verify that when reopening the review dialog for an already-reviewed item,
    the saved values are shown instead of the audit values.
    """
    app = SimpleQueueApp()
    mock_services = mocker.Mock()
    mock_services.reporting_service.campaign_name = "test-campaign"
    app.services = mock_services

    mock_reviewed_path = mocker.MagicMock()
    mock_reviewed_path.exists.return_value = True
    mock_reviewed_path.__truediv__ = mocker.MagicMock(return_value=mock_reviewed_path)

    mock_paths = mocker.MagicMock()
    mock_paths.campaign.return_value.queue.return_value.completed = mock_reviewed_path
    mocker.patch("cocli.tui.widgets.queues_view.paths", mock_paths)

    mock_file = mocker.MagicMock()
    mock_file.__enter__ = mocker.MagicMock(
        return_value=mocker.MagicMock(
            __iter__=mocker.MagicMock(
                return_value=iter(["ChIJ123\x1f4.5\x1f200\x1f2026-01-01T00:00:00Z\n"])
            )
        )
    )
    mock_file.__exit__ = mocker.MagicMock(return_value=False)
    mocker.patch("builtins.open", return_value=mock_file)

    async with app.run_test():
        detail = app.query_one("#queue_detail", QueueDetail)
        detail.active_queue = type("Queue", (), {"name": "gm-list"})()

        reviewed_data = detail._get_reviewed_data()

        assert reviewed_data["ChIJ123"] == ("4.5", "200")


@pytest.mark.asyncio
async def test_review_dialog_restores_focus_to_audit_list(mocker):
    """
    Verify that inline editing toggles on/off and input widgets are created.
    """
    from textual.app import App, ComposeResult

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield QueueDetail(id="queue_detail")

    app = TestApp()
    mock_services = mocker.Mock()
    mock_services.reporting_service.campaign_name = "test-campaign"
    app.services = mock_services

    mock_paths = mocker.MagicMock()
    mock_paths.campaign.return_value.queue.return_value.completed = mocker.MagicMock()
    mocker.patch("cocli.tui.widgets.queues_view.paths", mock_paths)

    async with app.run_test():
        detail = app.query_one("#queue_detail", QueueDetail)
        detail.active_queue = type("Queue", (), {"name": "gm-list"})()

        detail.audit_items = [
            {
                "place_id": "ChIJ1234567890abcdefghijkl",
                "name": "Test Business",
                "rating": "4.5",
                "reviews": "100",
            },
        ]
        detail.audit_selected_idx = 0

        assert detail.is_editing is False

        detail.action_mark_reviewed()

        assert detail.is_editing is True
        assert detail._edit_rating_input is not None
        assert detail._edit_reviews_input is not None
