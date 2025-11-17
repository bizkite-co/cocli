from textual.app import ComposeResult
from textual.containers import Horizontal, Container
from textual.widget import Widget

class MasterDetailView(Container):
    """A container that displays a master list and a detail view."""

    def __init__(self, master: Widget, detail: Widget, master_width: int = 30, name: str | None = None, id: str | None = None, classes: str | None = None):
        super().__init__(name=name, id=id, classes=classes)
        self.master_pane = master
        self.detail_pane = detail
        self.master_width = master_width

    def compose(self) -> ComposeResult:
        with Horizontal():
            master_container = Container(self.master_pane, id="master-pane")
            master_container.styles.width = self.master_width
            yield master_container
            yield Container(self.detail_pane, id="detail-pane")
