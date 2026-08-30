from pathlib import Path
from typing import Any, Optional

from textual import events
from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Static

from ..base import BaseModalScreen


class ScreenshotViewerModal(BaseModalScreen[None]):
    """Shows a company's captured website screenshot (see
    cocli/models/companies/website.py's screenshot_bytes field) as a
    quick "front face" preview - and lets the viewer flag the company as
    an illegitimate/ad-injected Google Maps result right from here, since
    that call is easier to make while actually looking at the site
    (Mark, 2026-08-29).

    Keys are handled directly via on_key, not BINDINGS - BaseModalScreen's
    default on_mount() calls self.focus() on the Screen itself, which
    isn't part of Textual's normal focus chain and leaves nothing
    focused, so plain BINDINGS silently never fire (confirmed empirically:
    app.focused was None after mount, and neither "escape" nor a custom
    binding dispatched). ConfirmScreen already established the reliable
    pattern this follows: an explicit can_focus=True + .focus() on a real
    child widget, plus a direct on_key() override.
    """

    def __init__(
        self,
        company_name: str,
        company_slug: str,
        domain: Optional[str],
        screenshot_path: Optional[Path],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.company_name = company_name
        self.company_slug = company_slug
        self.domain = domain
        self.screenshot_path = screenshot_path

    def compose(self) -> ComposeResult:
        with Container(id="screenshot_viewer"):
            yield Static(f"[bold]{self.company_name}[/]", id="screenshot_title")
            if self.screenshot_path and self.screenshot_path.exists():
                from textual_image.widget import AutoImage

                with Vertical(id="screenshot_frame"):
                    yield AutoImage(str(self.screenshot_path), id="screenshot_image")
            else:
                yield Static(
                    "[dim]No screenshot captured yet for this company - "
                    "re-enrich to capture one.[/]",
                    id="screenshot_missing",
                )
            yield Static(
                "[dim]\\[x] Flag illegitimate    \\[esc] Close[/]",
                id="screenshot_help",
            )

    def on_mount(self) -> None:
        super().on_mount()
        viewer = self.query_one("#screenshot_viewer")
        viewer.can_focus = True
        viewer.focus()

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            self.app.pop_screen()
        elif event.key == "x":
            self.run_worker(self.action_flag_illegitimate())

    async def action_flag_illegitimate(self) -> None:
        from .confirm_screen import ConfirmScreen

        confirm = await self.app.push_screen_wait(
            ConfirmScreen(
                f"Flag '{self.company_name}' as an illegitimate/ad-injected "
                "result and exclude it from this campaign?"
            )
        )
        if not confirm:
            return

        from ...core.config import get_campaign
        from ...core.exclusions import ExclusionManager

        campaign = get_campaign() or "default"
        ExclusionManager(campaign).add_exclusion(
            slug=self.company_slug,
            domain=self.domain,
            reason="google-maps-ad-injection",
        )
        self.app.notify(f"Excluded '{self.company_name}' from {campaign}")
        self.app.pop_screen()
