from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont
import yaml
from rich.console import Console

console = Console()

# YouTube recommended thumbnail size
_THUMB_W = 1280
_THUMB_H = 720

_FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

# White title (semi-transparent for overlay readability on busy screenshots)
_TITLE_FILL = (255, 255, 255, 220)
# Bold yellow subtext (full opacity for emphasis under the title)
_SUBTEXT_FILL = (255, 214, 0, 255)  # bright yellow


def parse_metadata(md_file: Path) -> Dict[str, Any]:
    """Parse YAML frontmatter from a markdown file."""
    if not md_file.exists():
        console.print(f"[red]Metadata file not found: {md_file}[/red]")
        return {}
    content = md_file.read_text()
    # YAML frontmatter is typically between --- and ---
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 2:
            try:
                data: Dict[str, Any] = yaml.safe_load(parts[1]) or {}
                console.print(f"[dim]Parsed metadata: {data}[/dim]")
                return data
            except yaml.YAMLError as e:
                console.print(f"[red]Error parsing YAML: {e}[/red]")
                return {}
    console.print("[yellow]No YAML frontmatter found.[/yellow]")
    return {}


def _normalize_overlay_text(text: str, *, uppercase: bool) -> str:
    text = text.replace("<br />", "\n").replace("<br/>", "\n").replace("<br>", "\n")
    if uppercase:
        text = text.upper()
    return text


def _fit_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_path: str,
    max_width: float,
    max_height: float,
    *,
    max_size: int = 200,
    min_size: int = 12,
    spacing: int = 0,
) -> Tuple[ImageFont.FreeTypeFont, int, int, int]:
    """Return (font, size, text_w, text_h) that fits inside max box."""
    font = ImageFont.truetype(font_path, min_size)
    best = (font, min_size, 0, 0)
    for size in range(min_size, max_size + 1):
        font = ImageFont.truetype(font_path, size)
        bbox = draw.multiline_textbbox(
            (0, 0), text, font=font, align="center", spacing=spacing
        )
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        if tw <= max_width and th <= max_height:
            best = (font, size, int(tw), int(th))
        else:
            break
    return best


def _wrap_line(text: str, font: ImageFont.FreeTypeFont, max_width: float) -> str:
    """Simple word-wrap so long subtext stays under the title block."""
    words = text.split()
    if not words:
        return text
    lines: list[str] = []
    current = words[0]
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    for word in words[1:]:
        trial = f"{current} {word}"
        bbox = probe.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return "\n".join(lines)


def overlay_text(
    image: Image.Image,
    text: str,
    subtext: Optional[str] = None,
) -> Image.Image:
    """
    Overlay title (and optional subtext) onto a screenshot.

    Title: bold white, uppercase, multi-line via ``<br/>``.
    Subtext: bold yellow, smaller, always drawn **below** the title block
    (not beside or overlapping title lines).
    """
    image = image.resize((_THUMB_W, _THUMB_H), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(image, "RGBA")

    title = _normalize_overlay_text(text, uppercase=True)
    sub = (
        _normalize_overlay_text(subtext, uppercase=False).strip()
        if subtext
        else ""
    )

    width, height = image.size
    pad_x = width * 0.06
    pad_y = height * 0.08
    max_w = width - 2 * pad_x

    # Title band upper; subtext always stacks under it with a clear gap
    if sub:
        title_max_h = height * 0.38
        sub_max_h = height * 0.22
        gap = max(20, int(height * 0.045))
    else:
        title_max_h = height * 0.85
        sub_max_h = 0.0
        gap = 0

    # Use real draw spacing when fitting so measured title_h matches rendered height
    title_spacing = 10
    title_font, title_size, title_w, title_h = _fit_font(
        draw,
        title,
        _FONT_BOLD,
        max_w,
        title_max_h,
        max_size=180,
        min_size=28,
        spacing=title_spacing,
    )
    title_spacing = max(8, int(title_size * 0.2))
    bbox = draw.multiline_textbbox(
        (0, 0), title, font=title_font, align="center", spacing=title_spacing
    )
    title_w = int(bbox[2] - bbox[0])
    title_h = int(bbox[3] - bbox[1])

    sub_font: Optional[ImageFont.FreeTypeFont] = None
    sub_w = sub_h = 0
    sub_size = 0
    sub_spacing = 6
    if sub:
        sub_font, sub_size, _, _ = _fit_font(
            draw,
            sub,
            _FONT_BOLD,
            max_w,
            sub_max_h,
            max_size=max(22, int(title_size * 0.4)),
            min_size=18,
            spacing=0,
        )
        sub = _wrap_line(sub, sub_font, max_w)
        sub_spacing = max(6, int(sub_size * 0.25))
        bbox = draw.multiline_textbbox(
            (0, 0), sub, font=sub_font, align="center", spacing=sub_spacing
        )
        sub_w = int(bbox[2] - bbox[0])
        sub_h = int(bbox[3] - bbox[1])
        if sub_h > sub_max_h and sub_size > 18:
            sub_size = max(18, int(sub_size * 0.85))
            sub_font = ImageFont.truetype(_FONT_BOLD, sub_size)
            sub = _wrap_line(sub, sub_font, max_w)
            bbox = draw.multiline_textbbox(
                (0, 0), sub, font=sub_font, align="center", spacing=sub_spacing
            )
            sub_w = int(bbox[2] - bbox[0])
            sub_h = int(bbox[3] - bbox[1])

    block_h = title_h + (gap + sub_h if sub else 0)
    # Center the title+subtext column as one stack
    y0 = max(pad_y, (height - block_h) / 2)

    overlay = Image.new("RGBA", image.size, (255, 255, 255, 0))
    draw_overlay = ImageDraw.Draw(overlay)

    title_x = (width - title_w) / 2
    draw_overlay.multiline_text(
        (title_x, y0),
        title,
        font=title_font,
        fill=_TITLE_FILL,
        align="center",
        spacing=title_spacing,
        stroke_width=max(1, title_size // 28),
        stroke_fill=(0, 0, 0, 160),
    )

    if sub and sub_font is not None:
        # Strictly below the measured title block
        sub_x = (width - sub_w) / 2
        sub_y = y0 + title_h + gap
        draw_overlay.multiline_text(
            (sub_x, sub_y),
            sub,
            font=sub_font,
            fill=_SUBTEXT_FILL,
            align="center",
            spacing=sub_spacing,
            stroke_width=max(1, sub_size // 22),
            stroke_fill=(0, 0, 0, 180),
        )

    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def process_thumbnail(video_dir: Path, output_dir: Path) -> None:
    """Finds thumbnail image and processes it if metadata exists."""
    md_file = video_dir / f"{video_dir.name}.md"
    console.print(f"[dim]Looking for metadata at: {md_file}[/dim]")
    metadata = parse_metadata(md_file)

    if metadata.get("thumbnail-style") != "text-overlay":
        console.print("[yellow]Metadata check failed: not text-overlay[/yellow]")
        return

    text = metadata.get("thumbnail-text")
    if not text:
        console.print("[yellow]No thumbnail text found[/yellow]")
        return

    subtext = metadata.get("thumbnail-subtext")
    if subtext is not None:
        subtext = str(subtext).strip() or None

    # Search for image based on metadata
    screenshot_name = metadata.get("thumbnail-screenshot")
    if screenshot_name:
        img_path = video_dir / str(screenshot_name)
    else:
        # Fallback to the first screenshot_*.png
        img_files = sorted(list(video_dir.glob("screenshot_*.png")))
        if not img_files:
            console.print(f"[red]No screenshots found in {video_dir}[/red]")
            return
        img_path = img_files[0]

    if not img_path.exists():
        console.print(f"[red]Screenshot file not found: {img_path}[/red]")
        return

    console.print(f"[dim]Processing thumbnail from: {img_path}[/dim]")
    if subtext:
        console.print(f"[dim]Subtext (below title): {subtext}[/dim]")
    image = Image.open(img_path)

    processed_image = overlay_text(image, str(text), subtext=subtext)

    # Save as PNG for lossless text
    output_path = output_dir / "thumbnail.png"
    output_dir.mkdir(parents=True, exist_ok=True)
    processed_image.save(output_path, format="PNG")
    console.print(f"[green]Saved processed thumbnail to: {output_path}[/green]")
