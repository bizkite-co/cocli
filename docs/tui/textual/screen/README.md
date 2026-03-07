# Screen TUI element

- Use folder-per-container "Screaming Architecture" TUI-matching.
- Use as-similar-as-possible screaming architecture TUI Python models.

Code like this could render the current implemented TUI structure, for comparison:

```python
def dump_tree(widget, indent=0):
    print(" " * indent + widget.__class__.__name__)
    for child in widget.children:
        dump_tree(child, indent + 4)
```
