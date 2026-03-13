import sys
import json
from cocli.core.secrets import get_secret_provider

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m cocli.utils.op_helper <item_id>")
        sys.exit(1)
        
    item_id = sys.argv[1]
    provider = get_secret_provider()
    item = provider.get_item(item_id)
    if not item:
        sys.exit(1)
        
    # Output as JSON for jq consumption
    print(json.dumps(item))

if __name__ == "__main__":
    main()
