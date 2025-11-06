from textual.app import ComposeResult
from textual.containers import Horizontal, Container
from textual.widget import Widget

class MasterDetailView(Container):
    """A container that displays a master list and a detail view."""

    def __init__(self, master: Widget, detail: Widget, name: str | None = None, id: str | None = None, classes: str | None = None):
        super().__init__(name=name, id=id, classes=classes)
        self.master_pane = master
        self.detail_pane = detail

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Container(self.master_pane, id="master-pane")
            yield Container(self.detail_pane, id="detail-pane")
