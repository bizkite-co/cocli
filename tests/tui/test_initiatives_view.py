"""InitiativesView: two-level list-above-a-list browser for a campaign's
initiatives/ folder tree, mirroring ApplicationView's Admin pattern
(top nav list + a stacked second list, h/j/k/l navigation)."""

from __future__ import annotations

import pytest
from textual.widgets import ListView

from cocli.application.services import ServiceContainer
from cocli.core.paths import paths
from cocli.tui.app import CocliApp
from cocli.tui.widgets.initiatives_view import (
    CategoryListItem,
    InitiativeListItem,
    InitiativesView,
    _EmailSequencesPane,
    _FileBrowserPane,
)

CAMPAIGN = "test/default"


def _make_initiative(campaign: str, initiative: str, categories: dict[str, dict[str, str]]) -> None:
    """categories: {category_name: {relative_file_path: content}}."""
    base = paths.campaigns / campaign / "initiatives" / initiative
    base.mkdir(parents=True, exist_ok=True)
    for category, files in categories.items():
        cat_dir = base / category
        for rel_path, content in files.items():
            file_path = cat_dir / rel_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")


@pytest.mark.asyncio
async def test_initiatives_list_populates_from_folder_names(mock_cocli_env, mocker) -> None:
    _make_initiative(CAMPAIGN, "rta", {"email-sequences": {"t.md": "x"}})
    _make_initiative(CAMPAIGN, "wealth-manager-products", {})

    app = CocliApp(services=ServiceContainer(campaign_name=CAMPAIGN), auto_show=False)
    async with app.run_test() as pilot:
        widget = InitiativesView()
        await app.main_content.mount(widget)
        await pilot.pause(0.2)

        list_view = widget.query_one("#initiatives_list", ListView)
        names = [i.initiative for i in list_view.children if isinstance(i, InitiativeListItem)]
        assert names == ["rta", "wealth-manager-products"]


@pytest.mark.asyncio
async def test_selecting_initiative_shows_only_existing_categories(mock_cocli_env, mocker) -> None:
    """A second initiative with no category folders yet must show an
    empty categories list, not a hardcoded fixed three."""
    _make_initiative(
        CAMPAIGN,
        "rta",
        {
            "email-sequences": {"t.md": "x"},
            "rendered-outreach": {"acme/t.md": "x"},
            "tracking": {"utm.csv": "x"},
        },
    )
    _make_initiative(CAMPAIGN, "wealth-manager-products", {})

    app = CocliApp(services=ServiceContainer(campaign_name=CAMPAIGN), auto_show=False)
    async with app.run_test() as pilot:
        widget = InitiativesView()
        await app.main_content.mount(widget)
        await pilot.pause(0.2)

        initiatives_list = widget.query_one("#initiatives_list", ListView)
        categories_list = widget.query_one("#categories_list", ListView)

        initiatives_list.focus()
        initiatives_list.index = 0  # rta
        await pilot.pause(0.1)
        await pilot.press("enter")
        await pilot.pause(0.2)

        cats = [c.category for c in categories_list.children if isinstance(c, CategoryListItem)]
        assert cats == ["email-sequences", "rendered-outreach", "tracking"]

        await pilot.press("h")
        await pilot.pause(0.1)
        assert initiatives_list.has_focus
        initiatives_list.index = 1  # wealth-manager-products
        await pilot.pause(0.1)
        await pilot.press("enter")
        await pilot.pause(0.2)

        cats2 = [c.category for c in categories_list.children if isinstance(c, CategoryListItem)]
        assert cats2 == []


@pytest.mark.asyncio
async def test_h_and_l_navigate_between_the_two_lists(mock_cocli_env, mocker) -> None:
    _make_initiative(CAMPAIGN, "rta", {"tracking": {"utm.csv": "x"}})

    app = CocliApp(services=ServiceContainer(campaign_name=CAMPAIGN), auto_show=False)
    async with app.run_test() as pilot:
        widget = InitiativesView()
        await app.main_content.mount(widget)
        await pilot.pause(0.2)

        initiatives_list = widget.query_one("#initiatives_list", ListView)
        categories_list = widget.query_one("#categories_list", ListView)

        initiatives_list.focus()
        initiatives_list.index = 0
        await pilot.pause(0.1)
        await pilot.press("l")
        await pilot.pause(0.2)
        assert categories_list.has_focus

        await pilot.press("h")
        await pilot.pause(0.1)
        assert initiatives_list.has_focus


@pytest.mark.asyncio
async def test_email_sequences_pane_renders_selected_template(mock_cocli_env, mocker) -> None:
    _make_initiative(
        CAMPAIGN,
        "rta",
        {"email-sequences": {"hook.md": '---\nsubject: "Hi {first_name}"\n---\n\nBody for {company_name}'}},
    )

    app = CocliApp(services=ServiceContainer(campaign_name=CAMPAIGN), auto_show=False)
    async with app.run_test() as pilot:
        widget = InitiativesView()
        await app.main_content.mount(widget)
        await pilot.pause(0.2)

        initiatives_list = widget.query_one("#initiatives_list", ListView)
        initiatives_list.focus()
        initiatives_list.index = 0
        await pilot.pause(0.1)
        await pilot.press("enter")
        await pilot.pause(0.2)

        categories_list = widget.query_one("#categories_list", ListView)
        categories_list.index = 0  # email-sequences
        await pilot.pause(0.1)
        await pilot.press("enter")
        await pilot.pause(0.2)

        pane = widget.query_one(_EmailSequencesPane)
        file_list = pane.query_one("#email_sequences_file_list", ListView)
        assert len(file_list.children) == 1
        file_list.focus()
        file_list.index = 0
        await pilot.pause(0.1)
        await pilot.press("enter")
        await pilot.pause(0.1)

        subject_label = pane.preview.query_one("#template-preview-subject")
        body_static = pane.preview.query_one("#template-preview-body")
        assert "Hi Sample" in str(subject_label.content)
        assert "Body for Sample Co" in str(body_static.content)


@pytest.mark.asyncio
async def test_file_browser_pane_shows_raw_content_for_tracking(mock_cocli_env, mocker) -> None:
    _make_initiative(CAMPAIGN, "rta", {"tracking": {"gtm-events.json": '{"hello": "world"}'}})

    app = CocliApp(services=ServiceContainer(campaign_name=CAMPAIGN), auto_show=False)
    async with app.run_test() as pilot:
        widget = InitiativesView()
        await app.main_content.mount(widget)
        await pilot.pause(0.2)

        initiatives_list = widget.query_one("#initiatives_list", ListView)
        initiatives_list.focus()
        initiatives_list.index = 0
        await pilot.pause(0.1)
        await pilot.press("enter")
        await pilot.pause(0.2)

        categories_list = widget.query_one("#categories_list", ListView)
        categories_list.index = 0  # tracking (only category present)
        await pilot.pause(0.1)
        await pilot.press("enter")
        await pilot.pause(0.2)

        pane = widget.query_one(_FileBrowserPane)
        file_list = pane.query_one("#file_browser_list", ListView)
        assert len(file_list.children) == 1
        file_list.focus()
        file_list.index = 0
        await pilot.pause(0.1)
        await pilot.press("enter")
        await pilot.pause(0.1)

        content_static = pane.preview.query_one("#file-browser-content")
        assert "hello" in str(content_static.content)
