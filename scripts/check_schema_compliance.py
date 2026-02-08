import os
import sys
from pathlib import Path

def check_compliance(campaign_name: str):
    schema_root = Path("docs/.schema/data-root/campaigns/CAMPAIGN_NAME")
    local_data_root = Path(os.getenv("COCLI_DATA_HOME", Path.home() / ".local/share/cocli_data"))
    campaign_dir = local_data_root / "campaigns" / campaign_name

    if not campaign_dir.exists():
        print(f"❌ Campaign directory not found: {campaign_dir}")
        return

    print(f"--- Schema Compliance Report: {campaign_name} ---")
    print(f"Data Root: {campaign_dir}\n")

    def walk_schema(schema_path: Path, local_path: Path, indent: int = 0):
        # Skip certain extensions
        if schema_path.suffix in [".md", ".mmd"]:
            return

        name = schema_path.name
        if name == "CAMPAIGN_NAME":
            name = campaign_name
            
        current_local = local_path
        
        # Display logic
        prefix = "  " * indent
        if current_local.exists():
            status = "✅"
            if current_local.is_file() and schema_path.is_file():
                # Potential for content/schema validation here
                pass
        else:
            status = "⚠️"
            
        print(f"{prefix}{status} {name}")

        if schema_path.is_dir():
            for child in sorted(schema_path.iterdir()):
                child_local = current_local / child.name
                walk_schema(child, child_local, indent + 1)

    walk_schema(schema_root, campaign_dir)

if __name__ == "__main__":
    campaign = sys.argv[1] if len(sys.argv) > 1 else "roadmap"
    check_compliance(campaign)
