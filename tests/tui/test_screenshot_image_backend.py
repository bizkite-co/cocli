"""Screenshot backend + rendered-output regression tests for the recurring
"double titles/headers" bug.

History: three prior fixes (57690e62, 5cb130c1, 7eada11e) suppressed
border_title and asserted on that suppression - which could never fail,
because CocliPanel.border_title is a property hardcoded to return "".
The real cause (2026-09-13): the textual_image Sixel widget injects raw
DCS + absolute-cursor escape sequences into Textual's differential
updates; terminals that mis-place the cursor or scroll during a sixel
draw (notably Windows Terminal) desync from the compositor and leave
stale rows, so pane/table headers appear twice. The default backend is
terminal detection (`auto`) with a self-healing Sixel wrapper that forces
a full-screen repaint after every sixel-injecting frame. These tests pin
the backend choice, the self-heal behavior, AND the actual rendered
output.
"""

import re
from typing import Any
from unittest.mock import MagicMock

import pytest
from textual.app import App

from cocli.application.services import ServiceContainer
from cocli.models.search import SearchResult
from cocli.utils.textual_utils import get_image_widget_class

TEXT_RE = re.compile(r'<text[^>]*?y="([0-9.]+)"[^>]*?>(.*?)</text>')


def svg_rows_by_y(svg: str) -> dict[float, list[str]]:
    """Group exported-screenshot text content by rendered row (y coordinate)."""
    rows: dict[float, list[str]] = {}
    for y, content in TEXT_RE.findall(svg):
        text = (
            content.replace("&#160;", " ")
            .replace("&gt;", ">")
            .replace("&lt;", "<")
            .replace("&amp;", "&")
            .strip()
        )
        if text:
            rows.setdefault(round(float(y), 1), []).append(text)
    return rows


def count_header_row_occurrences(svg: str, header: str) -> int:
    """Number of distinct rows the given header text is rendered on."""
    return sum(
        1
        for texts in svg_rows_by_y(svg).values()
        if any(t == header or t.startswith(header) for t in texts)
    )


class BareApp(App[None]):
    def compose(self):
        yield from ()


def test_default_backend_is_auto_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default follows textual_image's terminal detection.

    In headless test runs no graphics protocol is detected, so the alias
    resolves to AutoImage (text rendering); on a Sixel terminal it resolves
    to the self-healing SixelImage subclass (see test_sixel_backend_self_heals).
    """
    monkeypatch.delenv("COCLI_IMAGE_BACKEND", raising=False)
    import textual_image.widget as tiw

    cls = get_image_widget_class()
    if tiw.Image is tiw.SixelImage:
        assert issubclass(cls, tiw.SixelImage)
    else:
        assert cls is tiw.Image


def test_backend_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    import textual_image.widget as tiw

    monkeypatch.setenv("COCLI_IMAGE_BACKEND", "halfcell")
    assert get_image_widget_class() is tiw.HalfcellImage

    monkeypatch.setenv("COCLI_IMAGE_BACKEND", "unicode")
    assert get_image_widget_class() is tiw.UnicodeImage

    monkeypatch.setenv("COCLI_IMAGE_BACKEND", "tgp")
    assert get_image_widget_class() is tiw.TGPImage

    monkeypatch.setenv("COCLI_IMAGE_BACKEND", "none")
    assert get_image_widget_class() is None

    # Unknown values fall back to auto detection, not an error.
    monkeypatch.setenv("COCLI_IMAGE_BACKEND", "garbage")
    cls = get_image_widget_class()
    assert cls is not None
    if tiw.Image is tiw.SixelImage:
        assert issubclass(cls, tiw.SixelImage)
    else:
        assert cls is tiw.Image


def test_sixel_backend_returns_self_healing_subclass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The explicit sixel backend must be the self-healing wrapper, so the
    double-header fix cannot be bypassed by opting into graphics."""
    import textual_image.widget as tiw

    monkeypatch.setenv("COCLI_IMAGE_BACKEND", "sixel")
    cls = get_image_widget_class()
    assert cls is not None
    assert issubclass(cls, tiw.SixelImage)
    assert cls is not tiw.SixelImage
    assert get_image_widget_class() is cls  # cached, stable identity


@pytest.mark.asyncio
async def test_sixel_backend_self_heals(tmp_path, monkeypatch):
    """With the sixel backend forced, rendering an image must run the full
    two-stage heal cycle after the sixel-injecting frame: (1) a full
    absolute-positioned repaint (LayoutUpdate) that overwrites stale rows,
    then (2) a text-only pass over the rows below the image (ChopsUpdate
    whose bytes contain NO DCS payload - it cannot re-create the bottom-row
    corruption it exists to erase). The cycle must not self-perpetuate once
    external refreshes stop."""
    import io
    import time

    from PIL import Image as PILImage
    from rich.console import Console
    from textual._compositor import CompositorUpdate
    from textual_image.widget.sixel import _ImageSixelImpl

    monkeypatch.setenv("COCLI_IMAGE_BACKEND", "sixel")
    cls = get_image_widget_class()
    assert cls is not None

    png = tmp_path / "shot.png"
    PILImage.new("RGB", (164, 92), (10, 80, 160)).save(png)

    frames: list[tuple[str, bool]] = []  # (update class name, contains DCS)

    class RecordingApp(BareApp):
        def _display(self, screen, renderable) -> None:
            if isinstance(renderable, CompositorUpdate):
                console = Console(
                    file=io.StringIO(),
                    force_terminal=True,
                    color_system="truecolor",
                    legacy_windows=False,
                    safe_box=False,
                )
                data = renderable.render_segments(console)
                frames.append((type(renderable).__name__, "\x1bP" in data))
            super()._display(screen, renderable)

    app = RecordingApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.1)
        frames.clear()  # ignore the initial full render

        img = cls(str(png))
        # Explicit size so the impl widget gets a non-zero render region
        # (the real usage sites size it via #screenshot-panel CSS).
        img.styles.width = 80
        img.styles.height = 20
        await app.mount(img)
        await pilot.pause(0.15)

        impls = [w for w in app.query(_ImageSixelImpl)]
        assert impls, "expected the sixel impl widget to be mounted"
        impl = impls[0]

        names = [name for name, _ in frames]
        assert "ChopsUpdate" in names and frames[names.index("ChopsUpdate")][1], (
            "expected a sixel-injecting partial frame"
        )
        assert "LayoutUpdate" in names, "expected the stage-1 full repaint"
        tail = frames[names.index("LayoutUpdate") + 1 :]
        assert any(
            name == "ChopsUpdate" and not has_dcs for name, has_dcs in tail
        ), "expected a stage-2 text-only (DCS-free) pass after the full repaint"
        assert impl._resync_count >= 1
        assert not impl._heal_in_flight

        # Drive image-region updates for a while: every partial sixel frame
        # must get its own heal cycle (no time-dedupe blind window)...
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            impl.refresh()
            await pilot.pause(0.05)
        mid_count = impl._resync_count
        assert mid_count > 1, "heals must track each sixel frame, not a timer"

        # ...but once external refreshes stop, the cycle must converge and
        # stop by itself (flag-based loop-break, no self-perpetuation).
        settled_count = impl._resync_count
        await pilot.pause(0.6)
        assert impl._resync_count == settled_count, (
            f"heal cycle self-perpetuated: {settled_count} -> {impl._resync_count}"
        )
        assert not impl._heal_in_flight
        assert app.is_running


@pytest.mark.asyncio
async def test_sixel_payload_clamped_away_from_bottom_edge(tmp_path, monkeypatch):
    """The sixel payload's pixel height must stay half a cell short of the
    widget's allotted rows: Windows Terminal rasterizes a bottom-touching
    sixel with sub-cell overflow, scrolling the viewport and duplicating the
    last row (the stale-keymaps glitch). The clamp guarantees the payload
    cannot cross the widget's bottom edge."""
    import re

    from PIL import Image as PILImage

    from textual_image.widget.sixel import _ImageSixelImpl

    monkeypatch.setenv("COCLI_IMAGE_BACKEND", "sixel")

    # Deterministic cell size like the other headless captures.
    from textual_image import _terminal

    cell = _terminal.CellSize(width=10, height=20)
    import textual_image.widget.sixel as sixel_mod

    monkeypatch.setattr(sixel_mod, "get_cell_size", lambda: cell)

    cls = get_image_widget_class()
    assert cls is not None

    png = tmp_path / "shot.png"
    PILImage.new("RGB", (164, 92), (10, 80, 160)).save(png)

    app = BareApp()
    async with app.run_test(size=(120, 40)) as pilot:
        img = cls(str(png))
        img.styles.width = 80
        img.styles.height = 20
        await app.mount(img)
        await pilot.pause(0.15)

        impls = [w for w in app.query(_ImageSixelImpl)]
        assert impls
        cached = impls[0]._cached_sixels
        assert cached is not None, "expected the sixel data to be encoded"
        raster = re.search(r'"1;1;(\d+);(\d+)', cached.sixel_data)
        assert raster, "expected raster attributes in the sixel payload"
        pixel_height = int(raster.group(2))
        # 20 allotted rows * 20px cell - 10px half-cell slack = 390 max.
        assert pixel_height <= 20 * 20 - 10, (
            f"payload pixel height {pixel_height} reaches the widget's bottom "
            "edge; the overflow clamp is not applied"
        )


@pytest.mark.asyncio
async def test_company_detail_renders_single_header_rows(tmp_path, monkeypatch):
    """Rendered-output regression: with a screenshot present (the trigger for
    the Sixel path), every DetailPanel header must appear on exactly ONE row."""
    from PIL import Image as PILImage

    from cocli.tui.widgets.company_detail import CompanyDetail

    monkeypatch.delenv("COCLI_IMAGE_BACKEND", raising=False)

    enrichments = tmp_path / "enrichments"
    enrichments.mkdir()
    PILImage.new("RGB", (164, 92), (10, 80, 160)).save(
        enrichments / "screenshot.png"
    )

    company_data: dict[str, Any] = {
        "company": {
            "name": "Test Company",
            "slug": "backend-regression-co",
            "domain": "example.com",
        },
        "enrichment_path": str(enrichments / "website.md"),
        "contacts": [],
        "meetings": [],
        "notes": [],
        "emails": [],
    }

    app = BareApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await app.mount(CompanyDetail(company_data))  # type: ignore[arg-type]
        await pilot.pause(0.2)

        svg = app.export_screenshot()
        for header in ("COMPANY INFO", "CONTACTS", "ACTIVITY"):
            occurrences = count_header_row_occurrences(svg, header)
            assert occurrences == 1, (
                f"header {header!r} rendered on {occurrences} rows (expected 1)"
            )


@pytest.mark.asyncio
async def test_company_search_renders_single_pane_headers() -> None:
    """Rendered-output regression: the search view pane headers must each
    appear on exactly one row (the classic double-title symptom view)."""
    from cocli.tui.app import CocliApp
    from cocli.tui.widgets.company_search import CompanySearchView

    results = [
        SearchResult(
            name="Test Company 1",
            slug="test-company-1",
            domain="test1.com",
            type="company",
            unique_id="test-company-1",
            tags=[],
            display="",
        )
    ]
    mock_search = MagicMock()
    mock_search.return_value = results
    services = ServiceContainer(search_service=mock_search, sync_search=True)

    app = CocliApp(services=services, auto_show=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await app.action_show_companies()
        await pilot.pause(0.3)

        assert app.query_one(CompanySearchView) is not None
        svg = app.export_screenshot()
        for header in ("TEMPLATES", "PREVIEW"):
            occurrences = count_header_row_occurrences(svg, header)
            assert occurrences == 1, (
                f"header {header!r} rendered on {occurrences} rows (expected 1)"
            )
        # SEARCH header carries a live count suffix, e.g. "SEARCH (1 results)"
        assert count_header_row_occurrences(svg, "SEARCH (") == 1
