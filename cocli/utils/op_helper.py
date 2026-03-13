import sys
import json
from cocli.utils.op_utils import get_op_item

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m cocli.utils.op_helper <item_id>")
        sys.exit(1)
        
    item_id = sys.argv[1]
    item = get_op_item(item_id)
    if not item:
        sys.exit(1)
        
    # Output as JSON for jq consumption
    print(json.dumps(item))

if __name__ == "__main__":
    main()
