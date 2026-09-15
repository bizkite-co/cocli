"""Two-level "list-above-a-list" browser for a campaign's initiatives/
folder tree - mirrors ApplicationView's Admin-screen pattern (top nav
list + a stacked second list) one level down, inside the Messages
screen's content pane. Deliberately reads the real folder names/nesting
directly (via cocli.core.paths, not a merged abstraction) rather than
inventing a display layer over them, per the stated principle that TUI
navigation should track the actual folder structure - also prep for
treating Yazi as a supplemental UI over the same data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast, TYPE_CHECKING

if TYPE_CHECKING:
    from ..app import CocliApp

from textual import events, on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical

from textual.widgets import Label, ListItem, ListView

from ...core.paths import paths
from .message_templates_view import TemplateListItem, TemplatePreview

_CATEGORY_LABELS = {
    "email-sequences": "Email Sequences",
    "rendered-outreach": "Rendered Outreach",
    "tracking": "Tracking",
}


class InitiativeListItem(ListItem):
    def __init__(self, initiative: str) -> None:
        super().__init__()
        self.initiative = initiative

    def compose(self) -> Any:
        yield Label(self.initiative)


class CategoryListItem(ListItem):
    def __init__(self, category: str) -> None:
        super().__init__()
        self.category = category

    def compose(self) -> Any:
        yield Label(_CATEGORY_LABELS.get(self.category, self.category))


class FileBrowserListItem(ListItem):
    def __init__(self, path: Path, label: str) -> None:
        super().__init__()
        self.path = path
        self._label = label

    def compose(self) -> Any:
        yield Label(self._label)


class FileBrowserPreview(Container):
    def compose(self) -> Any:
        from textual.widgets import Static
        from textual.containers import VerticalScroll

        with VerticalScroll():
            yield Label("Select a file to preview it", id="file-browser-empty")
            yield Static("", id="file-browser-content")

    def update_preview(self, content: str | None) -> None:
        from textual.widgets import Static

        empty = self.query_one("#file-browser-empty", Label)
        body = self.query_one("#file-browser-content", Static)
        if content is None:
            empty.display = True
            body.update("")
            return
        empty.display = False
        body.update(content)


class _EmailSequencesPane(Horizontal):
    """Email Sequences category content: list_initiative_templates() +
    generate_copy() rendered with placeholder sample values, correctly
    scoped to whichever initiative is selected (not hardcoded)."""

    def __init__(self, initiative: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.initiative = initiative
        self.file_list = ListView(id="email_sequences_file_list")
        self.preview = TemplatePreview(id="email_sequences_preview")

    def compose(self) -> ComposeResult:
        yield Container(self.file_list, id="email-sequences-list-pane")
        yield self.preview

    async def on_mount(self) -> None:
        from cocli.application.personalized_outreach_service import PersonalizedOutreachService

        app = cast("CocliApp", self.app)
        campaign = app.services.campaign_name
        service = PersonalizedOutreachService(campaign)
        names = service.list_initiative_templates(self.initiative)
        for name in names:
            self.file_list.append(TemplateListItem(name))
        if not names:
            self.preview.update_preview(None, None)
        self.file_list.focus()

    @on(ListView.Selected)
    def on_template_selected(self, message: ListView.Selected) -> None:
        if not isinstance(message.item, TemplateListItem):
            return
        from cocli.application.personalized_outreach_service import PersonalizedOutreachService

        app = cast("CocliApp", self.app)
        campaign = app.services.campaign_name
        service = PersonalizedOutreachService(campaign)
        try:
            subject, body = service.generate_copy(
                first_name="Sample",
                company_name="Sample Co",
                company_slug="sample-co",
                template_name=message.item.template_name,
                initiative=self.initiative,
            )
        except Exception as e:
            self.app.notify(f"Template error: {e}", severity="error")
            self.preview.update_preview(
                "(template error)", f"{e}\n\nFix the placeholder before using this template in a batch."
            )
            return
        self.preview.update_preview(subject, body)

    def on_key(self, event: events.Key) -> None:
        if event.key == "j":
            self.file_list.action_cursor_down()
            event.prevent_default()
        elif event.key == "k":
            self.file_list.action_cursor_up()
            event.prevent_default()
        elif event.key == "h":
            self.app.query_one("#categories_list", ListView).focus()
            event.prevent_default()


class _FileBrowserPane(Horizontal):
    """Generic read-only file browser for Rendered Outreach / Tracking -
    list_category_files() for the list, raw file content for the preview."""

    def __init__(self, initiative: str, category: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.initiative = initiative
        self.category = category
        self.file_list = ListView(id="file_browser_list")
        self.preview = FileBrowserPreview(id="file_browser_preview")

    def compose(self) -> ComposeResult:
        yield Container(self.file_list, id="file-browser-list-pane")
        yield self.preview

    async def on_mount(self) -> None:
        from cocli.application.personalized_outreach_service import PersonalizedOutreachService

        app = cast("CocliApp", self.app)
        campaign = app.services.campaign_name
        service = PersonalizedOutreachService(campaign)
        base = paths.campaigns / campaign / "initiatives" / self.initiative / self.category
        files = service.list_category_files(self.initiative, self.category)
        for f in files:
            try:
                label = str(f.relative_to(base))
            except ValueError:
                label = f.name
            self.file_list.append(FileBrowserListItem(f, label))
        if not files:
            self.preview.update_preview(None)
        self.file_list.focus()

    @on(ListView.Selected)
    def on_file_selected(self, message: ListView.Selected) -> None:
        if not isinstance(message.item, FileBrowserListItem):
            return
        try:
            content = message.item.path.read_text(encoding="utf-8")
        except Exception as e:
            content = f"(could not read file: {e})"
        self.preview.update_preview(content)

    def on_key(self, event: events.Key) -> None:
        if event.key == "j":
            self.file_list.action_cursor_down()
            event.prevent_default()
        elif event.key == "k":
            self.file_list.action_cursor_up()
            event.prevent_default()
        elif event.key == "h":
            self.app.query_one("#categories_list", ListView).focus()
            event.prevent_default()


class InitiativesView(Container):
    """Master: initiatives list (top) + categories list (second, stacked
    below it in the same left column) - mirrors application_view.py's
    Admin nav_list/sub_nav pattern. Content pane (right) swaps between
    the Email Sequences render-preview pane and the generic file browser,
    per selected category."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.initiatives_list = ListView(id="initiatives_list")
        self.categories_list = ListView(id="categories_list")
        self.content_container: Container = Container(id="initiatives-content")
        self._current_initiative: str | None = None

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(id="initiatives-nav-column"):
                yield Label("INITIATIVES", classes="pane-header")
                yield self.initiatives_list
                yield Label("CATEGORY", classes="pane-header")
                yield self.categories_list
            yield self.content_container

    async def on_mount(self) -> None:
        from cocli.application.personalized_outreach_service import PersonalizedOutreachService

        app = cast("CocliApp", self.app)
        campaign = app.services.campaign_name
        service = PersonalizedOutreachService(campaign)
        for name in service.list_initiatives():
            self.initiatives_list.append(InitiativeListItem(name))
        # Deliberately no focus() call here - MessagesView._show_section()
        # controls focus externally via action_focus_master(), same as
        # every other section widget (none of them focus in on_mount either).
        # This matters on the very first Messages entry, where the outer
        # Sections sidebar must keep focus instead of this widget grabbing
        # it immediately (see MessagesView.on_mount()'s focus_content=False).

    def action_focus_master(self) -> None:
        """Matches the interface MessagesView._show_section() looks for on
        every section widget (MasterDetailView subclasses get this for
        free; InitiativesView isn't one, so it's defined explicitly)."""
        self.initiatives_list.focus()

    @on(ListView.Selected, "#initiatives_list")
    async def on_initiative_selected(self, event: ListView.Selected) -> None:
        if not isinstance(event.item, InitiativeListItem):
            return
        from cocli.application.personalized_outreach_service import PersonalizedOutreachService

        self._current_initiative = event.item.initiative
        app = cast("CocliApp", self.app)
        campaign = app.services.campaign_name
        service = PersonalizedOutreachService(campaign)

        await self.categories_list.clear()
        for category in service.list_initiative_categories(self._current_initiative):
            await self.categories_list.append(CategoryListItem(category))

        for child in list(self.content_container.children):
            await child.remove()

        if self.categories_list.children:
            self.categories_list.focus()

    @on(ListView.Selected, "#categories_list")
    async def on_category_selected(self, event: ListView.Selected) -> None:
        if not isinstance(event.item, CategoryListItem) or not self._current_initiative:
            return
        await self._show_category(self._current_initiative, event.item.category)

    async def _show_category(self, initiative: str, category: str) -> None:
        for child in list(self.content_container.children):
            await child.remove()

        pane: Horizontal
        if category == "email-sequences":
            pane = _EmailSequencesPane(initiative)
        else:
            pane = _FileBrowserPane(initiative, category)
        await self.content_container.mount(pane)

    def on_key(self, event: events.Key) -> None:
        focused = self.app.focused
        if focused is None:
            return

        if event.key == "h" and getattr(focused, "id", None) == "categories_list":
            self.initiatives_list.focus()
            event.prevent_default()
            event.stop()
            return

        if isinstance(focused, ListView) and focused.id in ("initiatives_list", "categories_list"):
            if event.key == "j":
                focused.action_cursor_down()
                event.prevent_default()
                event.stop()
            elif event.key == "k":
                focused.action_cursor_up()
                event.prevent_default()
                event.stop()
            elif event.key == "l":
                focused.action_select_cursor()
                event.prevent_default()
                event.stop()
