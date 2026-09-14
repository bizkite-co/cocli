from __future__ import annotations

import os
import re
from typing import Any, Optional

VALID_IMAGE_BACKENDS = ("auto", "halfcell", "sixel", "tgp", "unicode", "none")


def sanitize_id(text: str) -> str:
    """Sanitizes a string to be a valid Textual widget ID.

    Textual IDs must be `^[a-zA-Z_][a-zA-Z0-9_-]*$`.
    This function converts the text to lowercase, replaces invalid characters with
    hyphens, and prepends an underscore if the ID starts with a number.
    """
    if not text: # Handle empty string input
        return "_unknown-id"

    # Convert to lowercase
    sanitized = text.lower()
    # Replace invalid characters with hyphens
    sanitized = re.sub(r'[^a-z0-9_-]', '-', sanitized)
    # Remove leading/trailing hyphens
    sanitized = sanitized.strip('-')
    # If the ID starts with a number, prepend an underscore
    if sanitized and sanitized[0].isdigit():
        sanitized = f"_{sanitized}"

    if not sanitized: # If after sanitization, it becomes empty (e.g., input was only invalid chars)
        return "_unknown-id"

    return sanitized


_SELF_HEALING_SIXEL_IMAGE: Optional[type[Any]] = None
"""Cached self-healing SixelImage subclass (built lazily; see below)."""


def _build_self_healing_sixel_class() -> type[Any]:
    """Build (once) a SixelImage subclass that resyncs the terminal after
    every frame that injected sixel data.

    WHY: textual_image's Sixel widget injects raw DCS payloads plus
    absolute-cursor escapes into Textual's *differential* screen updates.
    Terminals that mis-handle the cursor or scroll during a sixel draw
    (notably Windows Terminal - see 2026-09-13 investigation; the stream
    cocli emits is internally consistent, the divergence is terminal-side)
    drift from the compositor and leave stale rows (doubled pane/table
    headers, and a stale duplicated keymap row above the Footer that no
    later repaint clears, because the compositor believes that row is
    already correct).

    Two defenses:

    1. PREVENT bottom overflow: clamp the sixel payload's pixel height to
       half a cell short of the widget's allotted rows (``_crop_image``
       override). WT rasterizes a sixel whose pixels reach the last content
       row with sub-cell overflow, scrolling the viewport and duplicating
       the bottom row; the slack absorbs cell-size rounding/DPI mismatch
       so the payload can never cross the widget's bottom edge. Half a
       cell of letterboxing is imperceptible.
    2. HEAL after every sixel frame (``render_lines`` hook): a full
       absolute-positioned repaint (stage 1), then a text-only pass over
       the rows BELOW the image (stage 2). Stage 2's refresh region does
       not intersect the image, so it contains no sixel injection and
       cannot re-create the very corruption it is erasing - this is what
       actually clears the stale keymap row that stage 1's own injection
       re-damages. A ``_heal_in_flight`` flag suppresses re-scheduling
       while a heal cycle is running (the heal frame itself re-renders the
       image), which breaks the self-perpetuating repaint loop
       structurally instead of by a time dedupe - there is no blind window
       where consecutive sixel frames go unhealed.
    """
    from textual.app import ComposeResult
    from textual.dom import NoScreen
    from textual.geometry import Region
    from textual.strip import Strip
    from textual_image._pixeldata import PixelData
    from textual_image._terminal import CellSize
    from textual_image.widget.sixel import Image as SixelImage
    from textual_image.widget.sixel import _ImageSixelImpl
    from textual_image.widget.sixel import _NoopRenderable

    class SelfHealingSixelImpl(_ImageSixelImpl):
        _heal_in_flight: bool = False
        _resync_count: int = 0

        def render_lines(self, crop: Region) -> list[Strip]:
            strips = super().render_lines(crop)
            self._schedule_post_sixel_resync()
            return strips

        def _crop_image(
            self, image: PixelData, crop: Region, terminal_sizes: CellSize
        ) -> PixelData:
            cropped = super()._crop_image(image, crop, terminal_sizes)
            max_height = max(
                1,
                crop.height * terminal_sizes.height
                - max(1, terminal_sizes.height // 2),
            )
            if cropped.height > max_height:
                cropped = cropped.scaled(
                    max(1, int(cropped.width * max_height / cropped.height)),
                    max_height,
                )
            return cropped

        def _schedule_post_sixel_resync(self) -> None:
            if self._heal_in_flight:
                # This render belongs to an in-flight heal cycle; scheduling
                # here would loop (heal frame -> render_lines -> schedule ...).
                return
            self._heal_in_flight = True
            self._resync_count += 1

            def heal() -> None:
                try:
                    screen = self.screen
                except NoScreen:
                    self._heal_in_flight = False
                    return
                # Stage 1: full repaint - every row rewritten at absolute
                # coordinates, overwriting stale rows everywhere.
                screen.refresh()

                def clean_bottom() -> None:
                    try:
                        screen = self.screen
                    except NoScreen:
                        self._heal_in_flight = False
                        return
                    # Stage 2: text-only pass over the rows below every
                    # sixel image. This region cannot contain an injection,
                    # so unlike stage 1 it cannot re-damage the bottom rows.
                    image_bottom = screen.size.height
                    for impl_widget in screen.query(_ImageSixelImpl):
                        try:
                            visible_bottom = (
                                screen.find_widget(impl_widget).visible_region.bottom
                            )
                        except Exception:
                            continue
                        image_bottom = min(image_bottom, visible_bottom)
                    if image_bottom < screen.size.height:
                        screen.refresh(
                            Region(
                                0,
                                image_bottom,
                                screen.size.width,
                                screen.size.height - image_bottom,
                            )
                        )
                    self._heal_in_flight = False

                self.call_after_refresh(clean_bottom)

            self.call_after_refresh(heal)

    class SelfHealingSixelImage(SixelImage, Renderable=_NoopRenderable):
        def compose(self) -> ComposeResult:
            yield SelfHealingSixelImpl(self.image, self._sixel_options)

    return SelfHealingSixelImage


def _self_healing_sixel_image() -> type[Any]:
    global _SELF_HEALING_SIXEL_IMAGE
    if _SELF_HEALING_SIXEL_IMAGE is None:
        _SELF_HEALING_SIXEL_IMAGE = _build_self_healing_sixel_class()
    return _SELF_HEALING_SIXEL_IMAGE


def get_image_widget_class() -> Optional[type[Any]]:
    """Screenshot rendering widget class for the TUI.

    Default `auto` (textual_image terminal detection): Sixel terminals get
    high-res graphics through a self-healing wrapper (payload clamped away
    from the widget's bottom edge + full repaint then clean bottom-rows pass
    after every sixel-injecting frame) that keeps terminals with sloppy
    sixel cursor/scroll handling (notably Windows Terminal) from leaving
    stale doubled header/keymap rows. Non-Sixel terminals fall back to
    halfcell-style text rendering, which needs no healing.

    Override with COCLI_IMAGE_BACKEND=auto|halfcell|sixel|tgp|unicode|none:
    `sixel` forces the (self-healing) Sixel widget even if undetected,
    `halfcell`/`unicode` force pure-text renderers (lower fidelity, work
    everywhere), `none` disables image rendering (callers fall back to a
    placeholder). Unknown values fall back to `auto`.
    """
    backend = os.environ.get("COCLI_IMAGE_BACKEND", "auto").strip().lower()

    # Import lazily: importing textual_image.widget queries the terminal for
    # its cell size, which only works before Textual claims it (CocliApp
    # triggers this early import in its own __init__).
    import textual_image.widget as tiw

    if backend == "halfcell":
        return tiw.HalfcellImage
    if backend == "unicode":
        return tiw.UnicodeImage
    if backend == "tgp":
        return tiw.TGPImage
    if backend == "none":
        return None
    if backend == "sixel":
        return _self_healing_sixel_image()

    # auto (default, and the fallback for unknown values)
    detected: type[Any] = tiw.Image
    if detected is tiw.SixelImage:
        return _self_healing_sixel_image()
    return detected
