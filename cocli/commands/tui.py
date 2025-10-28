import logging
from ..tui.app import CocliApp

logger = logging.getLogger(__name__)

def run_tui_app() -> None:
    """
    Launches the Textual TUI for cocli.
    """
    app = CocliApp()
    app.run()