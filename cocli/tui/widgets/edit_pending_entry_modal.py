"""Edit a pending batch entry's rendered subject/body before sending -
the "add my own text on top of the template" step (Mark, 2026-09-16),
so a due follow-up (or any pending batch row) doesn't have to be sent
as a raw, unpersonalized template render.
"""

from __future__ import annotations

from typing import Any

from textual import events, on
from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Label, Static, TextArea

from .inputs import CocliInput


class EditPendingEntryModal(ModalScreen[tuple[str, str] | None]):
    """Returns (subject, body) on save, None on cancel - the caller
    persists via PersonalizedOutreachService.update_pending_entry()."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+s", "save", "Save"),
    ]

    DEFAULT_CSS = """
    EditPendingEntryModal {
        align: center middle;
    }
    #edit-pending-form {
        width: 80;
        height: auto;
        max-height: 90%;
        background: #111111;
        border: double #00ff00;
        padding: 1 2;
    }
    #edit-pending-subject {
        width: 100%;
        margin-bottom: 1;
        border: tall #333333;
    }
    #edit-pending-body {
        height: 16;
        margin-bottom: 1;
        border: tall #333333;
    }
    """

    def __init__(self, subject: str, body: str, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._subject = subject
        self._body = body

    def compose(self) -> ComposeResult:
        with Container(id="edit-pending-form"):
            yield Label("EDIT BEFORE SENDING", id="edit-pending-title")
            yield Label("Subject", classes="field-label")
            yield CocliInput(value=self._subject, id="edit-pending-subject")
            yield Label("Body", classes="field-label")
            yield TextArea(self._body, id="edit-pending-body")
            yield Static(
                "[bold reverse] CTRL+S: SAVE [/]  [dim] ESC: CANCEL (no changes are lost - "
                "the original draft is untouched until you save) [/]",
                id="edit-pending-help",
            )

    def on_mount(self) -> None:
        self.query_one("#edit-pending-body", TextArea).focus()

    @on(events.Key)
    def handle_keys(self, event: events.Key) -> None:
        # TextArea swallows the screen binding; CallLogModal/
        # EmailComposeModal use the same pattern.
        if event.key == "ctrl+s":
            event.stop()
            event.prevent_default()
            self.action_save()

    def action_save(self) -> None:
        subject = self.query_one("#edit-pending-subject", CocliInput).value
        body = self.query_one("#edit-pending-body", TextArea).text
        self.dismiss((subject, body))

    def action_cancel(self) -> None:
        # Unlike CallLogModal/EmailComposeModal, cancelling here can't
        # lose real work - the underlying pending batch row is untouched
        # until Save is pressed, so no confirmation dialog is needed.
        self.dismiss(None)
