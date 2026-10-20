"""Slash-filter state shared by list panes.

The input row stays hidden until the operator opens it. While it is open
they are still typing. Enter records the query as executed, and the pane
header shows ``/query``. Escape puts the previous executed query back.
"""

from __future__ import annotations


class ListFilterState:
    def __init__(self) -> None:
        self.committed: str = ""
        self.editing: bool = False


def applied_header(base: str, state: ListFilterState) -> str:
    """Header text. The slash query appears only after Enter."""
    query = state.committed.strip()
    if state.editing or not query:
        return base
    return f"{base}  /{query}"


def commit_filter(state: ListFilterState, draft: str) -> None:
    state.committed = draft
    state.editing = False


def cancel_filter(state: ListFilterState, draft: str) -> str | None:
    """Leave editing. Return the query to restore when the draft changed."""
    state.editing = False
    if draft != state.committed:
        return state.committed
    return None


def clear_filter(state: ListFilterState) -> None:
    state.committed = ""
    state.editing = False
