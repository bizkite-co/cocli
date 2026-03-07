import asyncio
import os
import sys
from typing import IO, Any, List

# Ensure cocli is in the path
sys.path.append(os.getcwd())

from cocli.tui.app import CocliApp
from cocli.application.services import ServiceContainer

def dump_tree(widget: Any, indent: int = 0, file: IO[str] = sys.stdout, max_children: int = 3) -> None:
    node_id = f' (id="{widget.id}")' if getattr(widget, "id", None) else ""
    file.write(" " * indent + f"{widget.__class__.__name__}{node_id}\n")
    
    children: List[Any] = list(getattr(widget, "children", []))
    if not children:
        return

    # Strategy: 
    # 1. Group by class
    # 2. If a group has many items and most don't have IDs, condense them.
    # 3. Always show items with unique IDs if they are few.
    
    # For now, let's stick to a simpler "Smart Condense":
    # If children are mostly of the same type and many of them lack IDs, condense.
    
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

    # Default: dump all (or as many as we want)
    for child in children:
        dump_tree(child, indent + 4, file=file, max_children=max_children)

async def main() -> None:
    # Use a dummy service container if needed, but CocliApp should handle it
    services = ServiceContainer()
    app = CocliApp(services=services, auto_show=False)
    
    output_path = "docs/tui/screen/actual_tree.txt"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        async with app.run_test() as pilot:
            f.write("=== CocliApp Top Level ===\n")
            dump_tree(app, file=f)
            
            f.write("\n=== ApplicationView ===\n")
            await app.action_show_application()
            await pilot.pause()
            # The ApplicationView is mounted inside #app_content
            app_content = app.query_one("#app_content")
            dump_tree(app_content, file=f)

            f.write("\n=== CompanySearchView ===\n")
            await app.action_show_companies()
            await pilot.pause()
            dump_tree(app_content, file=f)

            f.write("\n=== PersonList ===\n")
            await app.action_show_people()
            await pilot.pause()
            dump_tree(app_content, file=f)

    print(f"TUI tree dumped to {output_path}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
