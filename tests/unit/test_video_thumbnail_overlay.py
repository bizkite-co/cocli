"""Thumbnail text-overlay: colors, position, process_thumbnail fixture."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from cocli.core.video.thumbnailer import (
    overlay_text,
    parse_rgba_color,
    process_thumbnail,
)


def test_parse_rgba_color_hex() -> None:
    assert parse_rgba_color("#ff0000", (0, 0, 0, 0)) == (255, 0, 0, 255)
    assert parse_rgba_color("00ff00aa", (0, 0, 0, 0)) == (0, 255, 0, 170)
    assert parse_rgba_color("#f00", (0, 0, 0, 0)) == (255, 0, 0, 255)
    assert parse_rgba_color("nope", (1, 2, 3, 4)) == (1, 2, 3, 4)


def _band_brightness(img: Image.Image, y0: int, y1: int) -> float:
    total = 0
    n = 0
    for y in range(y0, y1, 4):
        for x in range(0, img.size[0], 8):
            p = img.getpixel((x, y))
            total += int(p[0]) + int(p[1]) + int(p[2])
            n += 1
    return total / max(n, 1)


def test_overlay_subtext_below_title_and_position_top(tmp_path: Path) -> None:
    # Solid mid-gray base so text stroke is detectable
    base = Image.new("RGB", (640, 360), (80, 80, 80))
    out = overlay_text(
        base,
        "HELLO",
        subtext="world below",
        position="top",
        title_fill=(255, 255, 255, 255),
        subtext_fill=(255, 214, 0, 255),
    )
    assert out.size == (1280, 720)
    # Top third brighter than bottom third (title+sub stacked near top)
    top_b = _band_brightness(out, 0, 240)
    bottom_b = _band_brightness(out, 480, 720)
    assert top_b > bottom_b


def test_process_thumbnail_title_and_subtext_fixture(tmp_path: Path) -> None:
    slug = "demo-clip"
    video_dir = tmp_path / "normalized" / slug
    video_dir.mkdir(parents=True)
    out_dir = tmp_path / "packaged" / slug

    Image.new("RGB", (800, 450), (40, 60, 90)).save(
        video_dir / "screenshot_001.png"
    )
    (video_dir / f"{slug}.md").write_text(
        """---
title: Demo
thumbnail-style: text-overlay
thumbnail-text: "DEMO<br/>TITLE"
thumbnail-subtext: "sub under title"
thumbnail-position: center
thumbnail-title-color: "#FFFFFF"
thumbnail-subtext-color: "#FFD600"
thumbnail-screenshot: screenshot_001.png
draft: true
---

Body text ignored for thumbnail.
""",
        encoding="utf-8",
    )

    process_thumbnail(video_dir, out_dir)

    thumb = out_dir / "thumbnail.png"
    assert thumb.is_file()
    img = Image.open(thumb)
    assert img.size == (1280, 720)
    # Must differ from solid source (overlay painted)
    sample = [img.getpixel((x, y)) for y in range(0, 720, 40) for x in range(0, 1280, 40)]
    unique = len(set(sample))
    assert unique > 10
