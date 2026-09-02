"""Temporary Mark prefix (``m`` then a letter) as a one-line bar, not a modal."""

from __future__ import annotations

from typing import Any

from textual.widgets import Input, Static

MARK_PREFIX_HINT = "Mark: [i] invalid   [h] high-value   esc/alt+s cancel"


class MarkPrefixMixin:
    """Call ``handle_mark_prefix_key`` at the top of ``on_key``."""

    _mark_mode: bool = False

    def enter_mark_prefix(self) -> None:
        app = getattr(self, "app", None)
        focused = getattr(app, "focused", None) if app is not None else None
        if isinstance(focused, Input):
            return
        self._mark_mode = True
        bar = self.query_one("#mark-prefix-bar", Static)  # type: ignore[attr-defined]
        bar.update(MARK_PREFIX_HINT)
        bar.remove_class("hidden")

    def clear_mark_prefix(self) -> None:
        self._mark_mode = False
        try:
            bar = self.query_one("#mark-prefix-bar", Static)  # type: ignore[attr-defined]
            bar.update("")
            bar.add_class("hidden")
        except Exception:
            pass

    def handle_mark_prefix_key(self, event: Any) -> bool:
        if not getattr(self, "_mark_mode", False):
            return False
        if event.key == "i":
            self.clear_mark_prefix()
            self.action_mark_invalid()  # type: ignore[attr-defined]
        elif event.key == "h":
            self.clear_mark_prefix()
            self.action_mark_high_value()  # type: ignore[attr-defined]
        elif event.key in ("escape", "alt+s", "meta+s", "q"):
            self.clear_mark_prefix()
        event.stop()
        event.prevent_default()
        return True
