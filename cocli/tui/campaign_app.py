from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Input, Button, Static
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from typing import Any

from ..models.campaign import Campaign, CampaignImport, GoogleMaps, Prospecting
import toml
from cocli.core.config import get_campaign_dir

class EditValueScreen(ModalScreen):
    """Modal screen to edit a single value."""

    def __init__(self, initial_value: str, attribute_name: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial_value = initial_value
        self.attribute_name = attribute_name

    def compose(self) -> ComposeResult:
        with Vertical(id="edit_dialog"):
            yield Static(f"Editing {self.attribute_name}:")
            yield Input(value=self.initial_value, id="edit_input")
            with Horizontal(id="edit_buttons"):
                yield Button("Save", variant="primary", id="save_button")
                yield Button("Cancel", id="cancel_button")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save_button":
            new_value = self.query_one("#edit_input", Input).value
            self.dismiss(new_value)
        elif event.button.id == "cancel_button":
            self.dismiss(self.initial_value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "edit_input":
            self.dismiss(event.value)


class CampaignApp(App):
    """A Textual app to view campaign details."""

    CSS = """
    App {
        background: transparent;
    }
    """

    BINDINGS = [("q", "quit", "Quit"), ("j", "cursor_down", "Down"), ("k", "cursor_up", "Up"), ("e", "edit_cell", "Edit")]

    def __init__(self, campaign: Campaign, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.campaign = campaign

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        yield Footer()
        
        table = DataTable()
        table.add_column("Attribute", width=20)
        table.add_column("Value")
        
        for key, value in self.campaign.model_dump().items():
            if value is not None:
                table.add_row(key.replace('_', ' ').title(), str(value), key=key)

        yield table

    def action_cursor_down(self) -> None:
        self.query_one("DataTable").action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("DataTable").action_cursor_up()

    def action_edit_cell(self) -> None:
        table = self.query_one(DataTable)
        cell_key = table.cursor_coordinate
        if cell_key:
            row_index, _ = cell_key.row, cell_key.column
            displayed_attribute_name = table.get_cell_value((row_index, 0))
            # Convert displayed name back to model attribute name
            attribute_name = str(table.get_row_at(row_index).key)
            
            current_value = getattr(self.campaign, attribute_name, None)

            if isinstance(current_value, (str, int, float, bool)):
                def update_value(new_value: str) -> None:
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

                    setattr(self.campaign, attribute_name, converted_value)
                    self._save_campaign()
                    self.refresh_table()

                self.push_screen(EditValueScreen(str(current_value), displayed_attribute_name), update_value)
            elif isinstance(current_value, (list, dict, CampaignImport, GoogleMaps, Prospecting)):
                self.log(f"Editing of complex attribute '{displayed_attribute_name}' not yet supported. Use 'd' to drill down.")
            else:
                self.log(f"Cannot edit attribute '{displayed_attribute_name}' of type {type(current_value)}.")

    def _save_campaign(self) -> None:
        campaign_dir = get_campaign_dir(self.campaign.name)
        if not campaign_dir:
            self.log(f"Error: Campaign '{self.campaign.name}' directory not found.")
            return

        config_path = campaign_dir / "config.toml"
        if not config_path.exists():
            self.log(f"Error: Configuration file not found for campaign '{self.campaign.name}'.")
            return

        with open(config_path, "r") as f:
            config_data = toml.load(f)
        
        # Update the campaign section in config_data
        campaign_dict = self.campaign.model_dump(by_alias=True)
        config_data['campaign'] = {k: v for k, v in campaign_dict.items() if k not in ['import', 'google_maps', 'prospecting']}
        config_data['import'] = campaign_dict['import']
        config_data['google_maps'] = campaign_dict['google_maps']
        config_data['prospecting'] = campaign_dict['prospecting']

        with open(config_path, "w") as f:
            toml.dump(config_data, f)
        self.log(f"Campaign '{self.campaign.name}' saved successfully.")

    def refresh_table(self) -> None:
        table = self.query_one("DataTable")
        table.clear()
        table.add_column("Attribute", width=20)
        table.add_column("Value")
        for key, value in self.campaign.model_dump().items():
            if value is not None:
                table.add_row(key.replace('_', ' ').title(), str(value))
