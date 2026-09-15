"""Simple stats readout: sent count, unsubscribed count, and the computed
rate - no list+detail here, just numbers. Open rate is deliberately not
shown: no tracking infra exists yet (2026-09 decision)."""

from __future__ import annotations

from typing import Any, cast, TYPE_CHECKING

if TYPE_CHECKING:
    from ..app import CocliApp

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Label

from ..base import CocliPanel


class UnsubscribeRateView(CocliPanel):
    """Refreshes on mount/focus, same as TemplateList's count refresh."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(panel_title="UNSUBSCRIBE RATE", **kwargs)

    def compose(self) -> ComposeResult:
        yield Label("UNSUBSCRIBE RATE", classes="pane-header")
        with Vertical(id="unsubscribe-rate-stats"):
            yield Label("", id="unsubscribe-rate-sent")
            yield Label("", id="unsubscribe-rate-unsubscribed")
            yield Label("", id="unsubscribe-rate-rate")
            yield Label(
                "[dim]Open rate: not tracked (no infra yet)[/dim]",
                id="unsubscribe-rate-open-note",
            )

    def on_mount(self) -> None:
        self.refresh_stats()

    def on_focus(self) -> None:
        self.refresh_stats()

    def refresh_stats(self) -> None:
        from cocli.application.personalized_outreach_service import compute_unsubscribe_rate

        app = cast("CocliApp", self.app)
        campaign = app.services.campaign_name
        stats = compute_unsubscribe_rate(campaign)

        self.query_one("#unsubscribe-rate-sent", Label).update(f"Sent: {stats.sent_count:,}")
        self.query_one("#unsubscribe-rate-unsubscribed", Label).update(
            f"Unsubscribed: {stats.unsubscribed_count:,}"
        )
        self.query_one("#unsubscribe-rate-rate", Label).update(
            f"Rate: {stats.rate * 100:.1f}%"
        )
