import os
import sys
import re
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))
from cocli.models.schema_placeholders import SchemaPlaceholders

def check_compliance(campaign_name: str):
    schema_root = Path("docs/.schema/data-root/campaigns/{campaign_name}")
    
    # Use the current working directory 'data' symlink if it exists, otherwise fallback
    data_dir = Path("data").resolve()
    if not data_dir.exists():
        data_dir = Path(os.getenv("COCLI_DATA_HOME", Path.home() / ".local/share/cocli_data")).resolve()
    
    campaign_dir = (data_dir / "campaigns" / campaign_name).resolve()

    if not campaign_dir.exists():
        print(f"❌ Campaign directory not found: {campaign_dir}")
        return

    print(f"--- Schema Compliance Report: {campaign_name} ---")
    print(f"Data Root: {campaign_dir}\n")

    def walk_schema(schema_path: Path, local_path: Path, indent: int = 0):
        if schema_path.suffix in [".md", ".mmd"]:
            return

        name = schema_path.name
        # Match {variable} or {variable}.ext
        placeholder_match = re.search(r"\{([a-z_]+)\}", name)
        is_placeholder = bool(placeholder_match)
        
        prefix = "  " * indent

        if not is_placeholder:
            # Fixed directory or file
            if local_path.exists():
                print(f"{prefix}✅ {name}")
                if schema_path.is_dir():
                    # Recurse into schema children
                    for child in sorted(schema_path.iterdir()):
                        walk_schema(child, local_path / child.name, indent + 1)
            else:
                print(f"{prefix}⚠️ {name}")
        else:
            # Placeholder validation
            var_name = placeholder_match.group(1).upper()
            
            if var_name == "CAMPAIGN_NAME":
                # Print the actual campaign name
                print(f"{prefix}✅ {campaign_name} (as <{var_name}>)")
                for child in sorted(schema_path.iterdir()):
                    # When recursing from CAMPAIGN_NAME, we keep the same local_path 
                    # but append the child's name from the schema
                    walk_schema(child, local_path / child.name, indent + 1)
                return

            # Check parent for items matching the placeholder
            parent_local = local_path.parent
            if not parent_local.exists():
                return

            found_any = False
            match_count = 0
            try:
                items = sorted(list(parent_local.iterdir()))
                for item in items:
                    if item.name.startswith(".") or item.name in ["README.md", "datapackage.json"]:
                        continue
                    
                    # Ensure type match (dir vs file)
                    if schema_path.is_dir() != item.is_dir():
                        continue

                    val_name = item.name.split(".")[0]
                    if SchemaPlaceholders.validate_placeholder(var_name, val_name):
                        found_any = True
                        match_count += 1
                        
                        if match_count <= 2: 
                            print(f"{prefix}✅ {item.name} (matches <{var_name}>)")
                            if schema_path.is_dir():
                                for child in sorted(schema_path.iterdir()):
                                    # Recurse: next schema child against this matched local item's child
                                    walk_schema(child, item / child.name, indent + 1)
                        elif match_count == 3:
                            print(f"{prefix}... and more matches for <{var_name}>")
            except Exception:
                pass

            if not found_any:
                print(f"{prefix}⚠️ <{var_name}> (No matches found)")

    walk_schema(schema_root, campaign_dir)

if __name__ == "__main__":
    campaign = sys.argv[1] if len(sys.argv) > 1 else "roadmap"
    check_compliance(campaign)
