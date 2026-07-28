"""Shared Rich console formatting for OperationService.execute() runs.

OperationService.execute() drives named, step-based operations (see
OperationMetadata.steps) shared between the TUI and CLI. This module is the
one place that turns that step data into console output, so every command
that runs one of these operations - and any future decomposition/recomposition
of the steps themselves - looks the same and stays introspectable from the
metadata registry instead of being hand-formatted per call site.
"""

import re
from typing import Callable

from rich.console import Console

from ..application.operation_service import OperationMetadata

_STEP_RE = re.compile(r"^\[(\w+)\]\s*([^:]+):\s*(.*)$")

_ICONS = {
    "PENDING": ("→", "cyan"),
    "SUCCESS": ("✓", "green"),
    "ERROR": ("✗", "red"),
    "FAILURE": ("✗", "red"),
}


def print_operation_steps(console: Console, meta: OperationMetadata, indent: str = "  ") -> None:
    """Prints the operation's title and its declared step sequence up front."""
    console.print(f"[bold cyan]{meta.title}[/bold cyan] — {meta.description}")
    for i, step in enumerate(meta.steps, 1):
        console.print(f"{indent}[dim]{i}. {step.name} — {step.description}[/dim]")


def operation_log_callback(console: Console, indent: str = "  ") -> Callable[[str], None]:
    """Returns a log_callback for OperationService.execute() that renders
    each `[STATUS] step_name: details` line as a colored, iconified line."""

    def log_cb(msg: str) -> None:
        msg = msg.strip()
        if not msg:
            return
        match = _STEP_RE.match(msg)
        if not match:
            console.print(f"{indent}{msg}")
            return
        status, step, details = match.groups()
        icon, color = _ICONS.get(status, ("•", "white"))
        line = f"{indent}[{color}]{icon}[/{color}] [bold]{step}[/bold]"
        if details:
            line += f" — {details}"
        console.print(line)

    return log_cb
