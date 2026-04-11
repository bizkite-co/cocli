from pathlib import Path
from typing import Dict, Any
from PIL import Image, ImageDraw, ImageFont  # type: ignore
import yaml
from rich.console import Console

console = Console()


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


def overlay_text(image: Image.Image, text: str) -> Image.Image:
    """Overlay text onto an image with transparency."""
    # Resize image to YouTube standard (1280x720)
    image = image.resize((1280, 720), Image.Resampling.LANCZOS)

    draw = ImageDraw.Draw(image, "RGBA")
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

    # Handle multi-line and force uppercase for readability
    console.print(f"[dim]Processing text: {text}[/dim]")
    text = text.replace("<br />", "\n").upper()
    console.print(f"[dim]Transformed text: {text}[/dim]")

    # 1. Determine font size to fit with 10% padding
    width, height = image.size
    target_width = width * 0.9
    target_height = height * 0.9

    font_size = 1
    font = ImageFont.truetype(font_path, font_size)

    while True:
        bbox = draw.multiline_textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        if text_w > target_width or text_h > target_height:
            font_size -= 1
            font = ImageFont.truetype(font_path, font_size)
            break
        font_size += 1
        font = ImageFont.truetype(font_path, font_size)

    # Recalculate bbox for final font size
    bbox = draw.multiline_textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    # Center text
    x = (width - text_w) / 2
    y = (height - text_h) / 2

    # Create transparent layer
    overlay = Image.new("RGBA", image.size, (255, 255, 255, 0))
    draw_overlay = ImageDraw.Draw(overlay)

    # Draw text with 40% transparency (approx 102/255)
    draw_overlay.multiline_text(
        (x, y),
        text,
        font=font,
        fill=(255, 255, 255, 102),
        align="center",
        spacing=int(font_size * 0.5),
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

    # Search for image based on metadata
    screenshot_name = metadata.get("thumbnail-screenshot")
    if screenshot_name:
        img_path = video_dir / screenshot_name
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
    image = Image.open(img_path)

    processed_image = overlay_text(image, text)

    # Save as PNG for lossless text
    output_path = output_dir / "thumbnail.png"
    processed_image.save(output_path, format="PNG")
    console.print(f"[green]Saved processed thumbnail to: {output_path}[/green]")
