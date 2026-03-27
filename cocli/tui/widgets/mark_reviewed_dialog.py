import logging
import re
from typing import Any
from textual import events
from textual.widgets import Static, Input
from textual.containers import Vertical, Horizontal
from textual.app import ComposeResult
from textual.screen import ModalScreen

logger = logging.getLogger(__name__)


class MarkReviewedDialog(ModalScreen[dict[str, Any]]):
    """A modal dialog for entering/editing rating and reviews before marking as reviewed."""

    VALIDATE_RATING = re.compile(r"^\d*\.?\d{0,1}$")
    VALIDATE_REVIEWS = re.compile(r"^\d*$")

    def __init__(
        self,
        place_id: str,
        biz_name: str,
        current_rating: str,
        current_reviews: str,
        *args: Any,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self.place_id = place_id
        self.biz_name = biz_name
        self.current_rating = current_rating
        self.current_reviews = current_reviews

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static(f"Mark as Reviewed: {self.biz_name[:40]}", id="review-title"),
            Static(f"Place ID: {self.place_id}", id="review-place-id", classes="dim"),
            Static("", id="review-spacer"),
            Static("Rating (0-5, one decimal):", id="review-rating-label"),
            Input(value=self.current_rating, id="review-rating-input"),
            Static("Reviews count (non-negative integer):", id="review-reviews-label"),
            Input(value=self.current_reviews, id="review-reviews-input"),
            Static("", id="review-spacer2"),
            Horizontal(
                Static("([bold]Enter[/]) Save  ", id="review-save-hint"),
                Static("([bold]Esc[/]) Cancel", id="review-cancel-hint"),
            ),
            id="review-dialog",
        )

    def on_mount(self) -> None:
        input_widget = self.query_one("#review-rating-input", Input)
        input_widget.focus()

    def _validate_rating(self, value: str) -> bool:
        if not value:
            return True
        if not self.VALIDATE_RATING.match(value):
            return False
        try:
            return float(value) <= 5.0
        except ValueError:
            return False

    def _validate_reviews(self, value: str) -> bool:
        if not value:
            return True
        return bool(self.VALIDATE_REVIEWS.match(value))

    def on_input_changed(self, event: Input.Changed) -> None:
        input_id = event.input.id
        value = event.value
        if input_id == "review-rating-input":
            if value and not self._validate_rating(value):
                event.input.value = value[:-1]
        elif input_id == "review-reviews-input":
            if value and not self._validate_reviews(value):
                event.input.value = value[:-1]

    def on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            rating_input = self.query_one("#review-rating-input", Input)
            reviews_input = self.query_one("#review-reviews-input", Input)
            self.dismiss(
                {
                    "rating": rating_input.value,
                    "reviews": reviews_input.value,
                }
            )
        elif event.key == "escape":
            self.dismiss(None)
