import yaml
import os
from pathlib import Path
import logging
from typing import Any

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def email_address_constructor(loader: yaml.Loader, node: yaml.Node) -> Any:
    if isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node)
        return value[0] if value else ""
    # Mypy complains about Node type, but at runtime this works for ScalarNodes
    return loader.construct_scalar(node) # type: ignore

# Register constructor for BOTH SafeLoader and Loader
yaml.SafeLoader.add_constructor('tag:yaml.org,2002:python/object/new:cocli.models.email_address.EmailAddress', email_address_constructor)
yaml.Loader.add_constructor('tag:yaml.org,2002:python/object/new:cocli.models.email_address.EmailAddress', email_address_constructor)

def fix_file(file_path: Path) -> bool:
    content = file_path.read_text()
    if "!!python/object/new:cocli.models.email_address.EmailAddress" not in content:
        return False

    if not (content.startswith("---") and "---" in content[3:]):
        return False

    try:
        parts = content.split("---", 2)
        frontmatter_str = parts[1]
        markdown_content = parts[2]
        
        # Load with our custom constructor
        data = yaml.load(frontmatter_str, Loader=yaml.Loader)
        
        # Save with safe_dump
        new_frontmatter = yaml.safe_dump(data, sort_keys=False, default_flow_style=False, allow_unicode=True)
        
        new_content = f"---\n{new_frontmatter}---\n{markdown_content}"
        file_path.write_text(new_content)
        return True
    except Exception as e:
        logger.error(f"Error fixing {file_path}: {e}")
        return False

def cleanup_directory(base_dir: str) -> None:
    base_path = Path(base_dir)
    if not base_path.exists():
        logger.warning(f"Directory {base_dir} does not exist.")
        return

    count = 0
    fixed = 0
    for md_file in base_path.rglob("*.md"):
        if not md_file.exists():
            continue
        count += 1
        if fix_file(md_file):
            fixed += 1
        
        if count % 1000 == 0:
            logger.info(f"Checked {count} files, fixed {fixed}...")

    logger.info(f"Finished. Fixed {fixed} files in {base_dir}.")

if __name__ == "__main__":
    data_home = "/home/mstouffer/.local/share/cocli_data"
    
    cleanup_directory(os.path.join(data_home, "companies"))
    cleanup_directory(os.path.join(data_home, "people"))