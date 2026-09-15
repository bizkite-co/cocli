"""Top-level Messages branch (Space m). Thin wrapper around
InitiativesView, which owns the actual list-above-a-list navigation
(Initiatives top list, Category second list, mirroring ApplicationView's
Admin sidebar) - kept as a separate class so InitiativesView stays
independently mountable/testable. There is no longer a "Sections" picker
in front of it: the Initiatives/Category lists ARE the Messages sidebar,
the same way Admin's own nav_list/sub_nav ARE its sidebar - a wrapping
picker list here was a mistake, not a second navigation layer."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Container

from .initiatives_view import InitiativesView


class MessagesView(Container):
    """The Messages branch root (is_branch_root=True in app.py's nav_tree)."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.initiatives_view = InitiativesView()

    def compose(self) -> ComposeResult:
        yield self.initiatives_view

    async def on_mount(self) -> None:
        self.action_focus_master()

    def action_focus_sidebar(self) -> None:
        """Same conventional name app.py's action_navigate_up() already
        looks for (see CompanySearchView/PersonList) - this is what makes
        bare "h" ("Back") return focus to the Initiatives list instead of
        falling through to the no-active-node fallback."""
        self.initiatives_view.action_focus_master()

    def action_focus_master(self) -> None:
        """Matches the interface app.action_show_messages() expects when
        reusing an already-mounted view (same as EventCurationView, whose
        MasterDetailView base provides this - MessagesView isn't a
        MasterDetailView itself, so it's defined explicitly here)."""
        self.initiatives_view.action_focus_master()
