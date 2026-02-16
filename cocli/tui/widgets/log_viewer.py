import sys
import io
import contextlib
from typing import Iterator, Callable
from textual.app import ComposeResult
from textual.widgets import Static, Button
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen

class LogCapture(io.StringIO):
    """A StringIO subclass that posts a message whenever data is written."""
    def __init__(self, callback: Callable[[str], None]):
        super().__init__()
        self.callback = callback

    def write(self, s: str) -> int:
        res = super().write(s)
        if s.strip():
            self.callback(s)
        return res

@contextlib.contextmanager
def capture_logs(callback: Callable[[str], None]) -> Iterator[LogCapture]:
    """Context manager to capture stdout and stderr."""
    capture = LogCapture(callback)
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = capture
    sys.stderr = capture
    try:
        yield capture
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

class LogViewerModal(ModalScreen[None]):
    """A modal screen for viewing full operation logs."""
    
    def __init__(self, title: str, initial_content: str = ""):
        super().__init__()
        self.log_title = title
        self.initial_content = initial_content

    def compose(self) -> ComposeResult:
        with Container(id="log_viewer_container"):
            yield Static(f"[bold]{self.log_title}[/bold]", id="log_viewer_title")
            with VerticalScroll(id="log_viewer_content"):
                yield Static(self.initial_content, id="log_text")
            yield Button("Close", variant="primary", id="btn_close_log")

    def on_mount(self) -> None:
        self.query_one("#log_viewer_content").scroll_end(animate=False)

    def append_text(self, text: str) -> None:
        log_text = self.query_one("#log_text", Static)
        # Using _renderable which is the internal attribute for the content
        current = str(getattr(log_text, "_renderable", ""))
        log_text.update(current + text)
        self.query_one("#log_viewer_content").scroll_end(animate=False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_close_log":
            self.app.pop_screen()
