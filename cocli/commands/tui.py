import logging
from ..tui.app import CocliApp
from ..core.logging_config import setup_file_logging

logger = logging.getLogger(__name__)

def run_tui_app() -> None:

    """

    Launches the Textual TUI for cocli.

    """

    setup_file_logging("tui", file_level=logging.DEBUG, disable_console=True)

    app: CocliApp = CocliApp()

    app.run()
