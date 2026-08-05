# Video thumbnail text-overlay YAML contract

Package (`cocli video package` / `create-thumbnail`) reads frontmatter from
`normalized/{slug}/{slug}.md` (or packaged copy) and writes `thumbnail.png`.

## Required for overlay

```yaml
---
title: "My video title"
thumbnail-style: text-overlay
thumbnail-text: "BIG<br/>TITLE"
draft: true
---
```

| Field | Required | Description |
|-------|----------|-------------|
| `thumbnail-style` | yes | Must be `text-overlay` to enable processing |
| `thumbnail-text` | yes | Title lines; use `<br/>` for breaks; rendered **uppercase** white by default |
| `thumbnail-subtext` | no | Secondary line(s) in **bold yellow**, always **below** the title stack |
| `thumbnail-screenshot` | no | Source PNG name under the video dir; else first `screenshot_*.png` |
| `thumbnail-position` | no | Vertical stack placement: `top`, `center` (default), `bottom` |
| `thumbnail-title-color` | no | Title fill hex: `#RGB`, `#RRGGBB`, or `#RRGGBBAA` (default white) |
| `thumbnail-subtext-color` | no | Subtext fill hex (default bright yellow `#FFD600`) |

## Layout rules

- Output size: 1280×720 (YouTube recommended).
- Title and subtext are a **single vertical column**, horizontally centered.
- Subtext is **never** drawn beside or over title lines.
- Position shifts the whole stack (title+gap+subtext), not title alone.

## Example

```yaml
---
title: "Task Agent Intro"
thumbnail-style: text-overlay
thumbnail-text: "TASK AGENT<br/>INTRO"
thumbnail-subtext: "Capture · Plan · Ship"
thumbnail-position: top
thumbnail-title-color: "#FFFFFF"
thumbnail-subtext-color: "#FFD600"
thumbnail-screenshot: screenshot_002.png
draft: true
---
```

## Re-package only

After editing YAML:

```bash
cocli video create-thumbnail <slug> -c <campaign>
# or full package with --force
cocli video package -c <campaign> --force
```

Re-upload path for **thumbnail-only** changes on an already-uploaded video is
not automated yet; use YouTube Studio or a future upload-thumbnail command.
