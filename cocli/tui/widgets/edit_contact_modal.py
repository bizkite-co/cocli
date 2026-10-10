# POLICY: frictionless-data-policy-enforcement
from __future__ import annotations

from typing import Optional

from textual import on, events
from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Label, Static

from ...models.people.person import Person
from .inputs import CocliInput


class EditContactModal(ModalScreen[bool]):
    """Edits a Person record's phone/email/role/profile_url fields.

    Mark, 2026-10-09: this replaces the "Edit Contact coming soon" stub
    that used to sit behind the Contacts panel's i/Enter binding - there
    was no way to fix a wrong contact phone/email, or record a person's
    bio page (e.g. https://www.higginbotham.com/team/mitchell-gaylord/),
    short of hand-editing the person's .md file. Only Person-backed
    contact rows (ones with a "slug" key) are editable here - website-
    scraped or email-context rows aren't real Person records and have
    nowhere to save to.

    Dismisses with True if saved, False on cancel.
    """

    DEFAULT_CSS = """
    EditContactModal {
        align: center middle;
    }
    #edit_contact_form {
        width: 70;
        height: auto;
        border: round $primary;
        background: $surface;
        padding: 1 2;
    }
    #edit_contact_title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    #edit_contact_help {
        margin-top: 1;
        text-align: center;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+s", "save", "Save"),
    ]

    def __init__(self, person_slug: str, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.person_slug = person_slug

    def compose(self) -> ComposeResult:
        person = Person.get(self.person_slug)
        name = str(person.name) if person and person.name else ""
        email = str(person.email) if person and person.email else ""
        phone = str(person.phone) if person and person.phone else ""
        role = person.role if person and person.role else ""
        profile_url = person.profile_url if person and person.profile_url else ""

        with Container(id="edit_contact_form"):
            yield Label(f"EDIT CONTACT: [bold cyan]{name or self.person_slug}[/]", id="edit_contact_title")

            yield Label("Name", classes="field-label")
            yield CocliInput(value=name, id="edit_contact_name")

            yield Label("Email", classes="field-label")
            yield CocliInput(value=email, id="edit_contact_email")

            yield Label("Phone", classes="field-label")
            yield CocliInput(value=phone, id="edit_contact_phone")

            yield Label("Role", classes="field-label")
            yield CocliInput(value=role, id="edit_contact_role")

            yield Label("Profile URL (bio/team page)", classes="field-label")
            yield CocliInput(value=profile_url, id="edit_contact_profile_url")

            yield Static(
                "[bold reverse] CTRL+S: SAVE [/]  [dim] ESC: CANCEL [/]",
                id="edit_contact_help",
            )

    def on_mount(self) -> None:
        self.query_one("#edit_contact_name", CocliInput).focus()

    @on(events.Key)
    def handle_keys(self, event: events.Key) -> None:
        if event.key == "ctrl+s":
            self.action_save()
            event.prevent_default()
            event.stop()

    def action_cancel(self) -> None:
        self.dismiss(False)

    def action_save(self) -> None:
        person = Person.get(self.person_slug)
        if person is None:
            self.app.notify(f"Contact '{self.person_slug}' not found", severity="error")
            return

        def _field(widget_id: str) -> Optional[str]:
            value = self.query_one(widget_id, CocliInput).value.strip()
            return value or None

        data = person.model_dump(exclude_none=True)
        data["name"] = _field("#edit_contact_name")
        data["email"] = _field("#edit_contact_email")
        data["phone"] = _field("#edit_contact_phone")
        data["role"] = _field("#edit_contact_role")
        data["profile_url"] = _field("#edit_contact_profile_url")

        try:
            updated = Person(**data)
        except Exception as exc:
            self.app.notify(f"Invalid contact data: {exc}", severity="error")
            return

        updated.save(person_file=person.get_file_path())
        self.app.notify(f"Saved contact {updated.name or self.person_slug}")
        self.dismiss(True)
