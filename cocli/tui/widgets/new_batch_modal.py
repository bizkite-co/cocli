# POLICY: frictionless-data-policy-enforcement
from __future__ import annotations

from typing import Optional

from textual import on, events
from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Label, Static

from .inputs import CocliInput
from .search_select import SearchSelect


class NewBatchModal(ModalScreen[Optional[tuple[int, str]]]):
    """Prompts for a limit and a template, then dismisses with (limit,
    template_id) - or None on cancel. Freezing (not sending) happens in
    the caller, same shape as CallLogModal."""

    BINDINGS = [
        ("escape", "dismiss(None)", "Cancel"),
        ("ctrl+s", "save", "Prepare Batch"),
    ]

    def __init__(self, templates: list[str], *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.templates = templates or ["email_01_pas_hook.md"]

    def compose(self) -> ComposeResult:
        with Container(id="new_batch_form"):
            yield Label("NEW BATCH", id="new_batch_title")
            yield Label("Limit (max recipients)", classes="field-label")
            yield CocliInput(value="10", id="new_batch_limit")
            yield Label("Template (type to filter, Enter to pick)", classes="field-label")
            yield SearchSelect(
                [(name, name) for name in self.templates],
                initial_value=self.templates[0],
                id="new_batch_template",
            )
            yield Static("[bold reverse] CTRL+S: PREPARE [/]  [dim] ESC: CANCEL [/]", id="modal_help")

    def on_mount(self) -> None:
        self.query_one("#new_batch_limit", CocliInput).focus()

    @on(events.Key)
    def handle_keys(self, event: events.Key) -> None:
        if event.key == "ctrl+s":
            self.action_save()

    def action_save(self) -> None:
        raw_limit = self.query_one("#new_batch_limit", CocliInput).value.strip()
        try:
            limit = int(raw_limit)
        except ValueError:
            self.app.notify("Limit must be a number", severity="error")
            return
        if limit <= 0:
            self.app.notify("Limit must be positive", severity="error")
            return

        template_id = self.query_one("#new_batch_template", SearchSelect).value
        if not template_id:
            self.app.notify("Pick a template", severity="error")
            return

        self.dismiss((limit, template_id))
