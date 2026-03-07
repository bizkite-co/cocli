# TUI Screen Structure

This directory contains the documentation for the cocli TUI screen layout.

## Convention

- **DSL:** Uses Python class names to represent the Textual widget hierarchy.
- **Directories:** Snake case representation of the widget or its ID.

## Top-Level Structure

```text
Screen {
    MenuBar
    Container(id="app_content")
    Footer
}
```
## Strategy

- Use folder-per-container "Screaming Architecture" TUI-matching.
- Use as-similar-as-possible screaming architecture TUI Python models.

Code like this could render the current implemented TUI structure, for comparison:

```python
def dump_tree(widget, indent=0):
    print(" " * indent + widget.__class__.__name__)
    for child in widget.children:
        dump_tree(child, indent + 4)
```

