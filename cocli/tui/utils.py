import sys
from typing import IO, Any, List

def dump_tree(widget: Any, indent: int = 0, file: IO[str] = sys.stdout, max_children: int = 3) -> None:
    """
    Recursively dumps the widget tree of a Textual widget or app.
    Uses 'Smart Condensing' to summarize repetitive items without IDs.
    """
    node_id = f' (id="{widget.id}")' if getattr(widget, "id", None) else ""
    file.write(" " * indent + f"{widget.__class__.__name__}{node_id}\n")
    
    children: List[Any] = list(getattr(widget, "children", []))
    if not children:
        return

    if len(children) > max_children + 1:
        # Check if the children are repetitive (same class, mostly no IDs)
        first_class = children[0].__class__.__name__
        all_same_class = all(c.__class__.__name__ == first_class for c in children)
        mostly_no_ids = sum(1 for c in children if not getattr(c, "id", None)) > (len(children) / 2)
        
        if all_same_class and mostly_no_ids:
            # Show first few
            for child in children[:max_children]:
                dump_tree(child, indent + 4, file=file, max_children=max_children)
            file.write(" " * (indent + 4) + f"... and {len(children) - max_children} more {first_class} items\n")
            return

    # Default: dump all
    for child in children:
        dump_tree(child, indent + 4, file=file, max_children=max_children)
