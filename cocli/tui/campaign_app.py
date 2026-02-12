from __future__ import annotations

from textual import events
from textual.screen import Screen, ModalScreen
from textual.widgets import DataTable, Input, Static # Removed Header, Footer
from textual.containers import Vertical
from textual.app import ComposeResult # Added ComposeResult import
from typing import Any

from ..models.campaign import Campaign, CampaignImport, GoogleMaps, Prospecting

from ..application.campaign_service import CampaignService

import logging

logger = logging.getLogger(__name__)

class EditValueScreen(ModalScreen[Any]):
    """Modal screen to edit a single value."""

    BINDINGS = [("ctrl+s", "save", "Save"), ("ctrl+c", "cancel", "Cancel")]

    def __init__(self, initial_value: str, attribute_name: str, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.initial_value = initial_value
        self.attribute_name = attribute_name

    def compose(self) -> ComposeResult:
        with Vertical(id="edit_dialog"):
            yield Static(f"Editing {self.attribute_name}:")
            yield Input(value=self.initial_value, id="edit_input")
            yield Static("([bold]s[/])ave, ([bold]c[/])ancel")

    def on_key(self, event: events.Key) -> None:
        if event.key == "ctrl+s":
            new_value = self.query_one("#edit_input", Input).value
            self.dismiss(new_value)
        elif event.key == "ctrl+c":
            self.dismiss(None)

class EditListScreen(ModalScreen[Any]):
    """Modal screen to edit a list of strings."""

    BINDINGS = [("ctrl+a", "add", "Add"), ("ctrl+d", "delete", "Delete"), ("ctrl+s", "save", "Save"), ("ctrl+c", "cancel", "Cancel")]

    def __init__(self, initial_list: list[str], attribute_name: str, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.initial_list = initial_list
        self.attribute_name = attribute_name

    def compose(self) -> ComposeResult:
        with Vertical(id="edit_list_dialog"):
            yield Static(f"Editing {self.attribute_name}:")
            for item in self.initial_list:
                yield Input(value=item)
            yield Static("([bold]a[/])dd, ([bold]d[/])elete, ([bold]s[/])ave, ([bold]c[/])ancel")

    def on_key(self, event: events.Key) -> None:
        if event.key == "ctrl+s":
            new_list = [i.value for i in self.query(Input)]
            self.dismiss(new_list)
        elif event.key == "ctrl+c":
            self.dismiss(None)
        elif event.key == "ctrl+a":
            self.query_one("#edit_list_dialog").mount(Input())
        elif event.key == "ctrl+d":
            if self.query(Input):
                self.query(Input)[-1].remove()

class EditObjectScreen(ModalScreen[Any]):
    """Modal screen to edit an object."""

    BINDINGS = [("ctrl+s", "save", "Save"), ("ctrl+c", "cancel", "Cancel")]

    def __init__(self, initial_object: dict[str, Any], attribute_name: str, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.initial_object = initial_object
        self.attribute_name = attribute_name

    def compose(self) -> ComposeResult:
        with Vertical(id="edit_object_dialog"):
            yield Static(f"Editing {self.attribute_name}:")
            for key, value in self.initial_object.items():
                yield Static(key)
                yield Input(value=str(value), id=key)
            yield Static("([bold]s[/])ave, ([bold]c[/])ancel")

    def on_key(self, event: events.Key) -> None:
        if event.key == "ctrl+s":
            new_object = {}
            for key, _ in self.initial_object.items():
                new_object[key] = self.query_one(f"#{key}", Input).value
            self.dismiss(new_object)
        elif event.key == "ctrl+c":
            self.dismiss(None)

class CampaignScreen(Screen[None]): # Changed from App to Screen
    """A Textual screen to view campaign details."""

    CSS = """
    CampaignScreen { # Changed from App
        background: transparent;
    }
    """

    BINDINGS = [
        ("q", "dismiss", "Quit"), # Changed action from quit to dismiss
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
        ("e", "edit_cell", "Edit"),
        ("d", "drill_down", "Drill Down")
    ]

    def __init__(self, campaign: Campaign, name: str | None = None, id: str | None = None, classes: str | None = None):
        super().__init__(name=name, id=id, classes=classes)
        self.campaign = campaign
        self.service = CampaignService(campaign.name)

    def compose(self) -> ComposeResult:
        """Create child widgets for the screen."""
        # Removed Header and Footer here, as they belong to the main App
        
        table: DataTable[Any] = DataTable()
        table.add_column("Key", key="key", width=0)
        table.add_column("Attribute", key="attribute", width=20)
        table.add_column("Value", key="value")
        
        for key, value in self.campaign.model_dump().items():
            if value is not None:
                table.add_row(key, key.replace('_', ' ').title(), str(value))

        yield table

    def action_cursor_down(self) -> None:
        table = self.query_one(DataTable)
        table.action_cursor_down()

    def action_cursor_up(self) -> None:
        table = self.query_one(DataTable)
        table.action_cursor_up()

    def _save_campaign(self) -> None:
        self.service.save_config(self.campaign)

    def refresh_table(self) -> None:
        table: DataTable[Any] = self.query_one(DataTable)
        table.clear()
        for key, value in self.campaign.model_dump().items():
            if value is not None:
                table.add_row(key, key.replace('_', ' ').title(), str(value))

    async def action_edit_cell(self) -> None:
        table = self.query_one(DataTable)
        cell_key = table.cursor_coordinate
        if not cell_key.row:
            return
        
        row_key = table.get_row_at(table.cursor_row)[0]
        attribute_name = str(row_key)
        
        current_value = getattr(self.campaign, attribute_name, None)

        if isinstance(current_value, (str, int, float, bool)):
            new_value = await self.app.push_screen(EditValueScreen(str(current_value), attribute_name))
            if new_value is None:
                return
            
            converted_value: Any # Use Any for now to avoid type issues with mixed types
            # Attempt to convert new_value to the correct type
            if isinstance(current_value, int):
                converted_value = int(new_value)
            elif isinstance(current_value, float):
                converted_value = float(new_value)
            elif isinstance(current_value, bool):
                converted_value = new_value.lower() == 'true'
            else:
                converted_value = new_value

            self.campaign = self.campaign.model_copy(update={attribute_name: converted_value})
            self._save_campaign()
            self.refresh_table()
        elif isinstance(current_value, (list, dict, CampaignImport, GoogleMaps, Prospecting)):
            self.log(f"Editing of complex attribute '{attribute_name}' not yet supported. Use 'd' to drill down.")
        else:
            self.log(f"Cannot edit attribute '{attribute_name}' of type {type(current_value)}.")
        return None
    async def action_drill_down(self) -> None:
        table = self.query_one(DataTable)
        cell_key = table.cursor_coordinate
        if not cell_key.row:
            return

        row_key = table.get_row_at(table.cursor_row)[0]
        attribute_name = str(row_key)

        current_value = getattr(self.campaign, attribute_name, None)

        if isinstance(current_value, list):
            new_list = await self.app.push_screen(EditListScreen(current_value, attribute_name))
            if new_list is None:
                return

            setattr(self.campaign, attribute_name, new_list)
            self._save_campaign()
            self.refresh_table()

        elif isinstance(current_value, (dict, CampaignImport, GoogleMaps, Prospecting)):
            if isinstance(current_value, dict):
                new_object = await self.app.push_screen(EditObjectScreen(current_value, attribute_name))
            else:
                new_object = await self.app.push_screen(EditObjectScreen(current_value.model_dump(), attribute_name))
            if new_object is None:
                return

            setattr(self.campaign, attribute_name, new_object)
            self._save_campaign()
            self.refresh_table()
        else:
            self.log(f"Cannot drill down into attribute '{attribute_name}' of type {type(current_value)}.")
        return None