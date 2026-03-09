import json
import logging
from pathlib import Path
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field
from enum import Enum
from cocli.core.paths import paths
from cocli.core.constants import UNIT_SEP
from .schema_source import SchemaSource

logger = logging.getLogger(__name__)

class AuditStatus(str, Enum):
    VALID = "VALID"
    MISSING = "MISSING"
    ORPHAN = "ORPHAN"
    ERROR = "ERROR"
    NON_CONFORMING = "NON_CONFORMING" # For row-level schema errors

class AuditNode(BaseModel):
    name: str
    path: Path
    status: AuditStatus
    is_dir: bool
    children: List['AuditNode'] = Field(default_factory=list)
    message: Optional[str] = None
    stats: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}

class FsAuditor:
    """
    Audits the filesystem for OMAP (Ordinant Mapping) compliance.
    Compares Actual state vs Expected "Screaming Architecture" rules.
    """
    def __init__(self, root: Optional[Path] = None, schema_root: Optional[Path] = None):
        self.root = root or paths.root
        self.schema_root = schema_root or (Path(__file__).parent.parent.parent.parent / "docs" / "_schema" / "data-root")
        self.schema = SchemaSource(self.schema_root)
        
    def audit_full(self, campaign_name: Optional[str] = None) -> AuditNode:
        """Performs a full recursive audit of the data root."""
        root_node = AuditNode(
            name="data_root",
            path=self.root,
            is_dir=True,
            status=AuditStatus.VALID
        )
        
        # We walk the real filesystem and match against schema
        self._recursive_audit(self.root, root_node, campaign_name)
        return root_node

    def _recursive_audit(self, current_path: Path, parent_node: AuditNode, campaign_filter: Optional[str] = None) -> None:
        try:
            for item in current_path.iterdir():
                # Skip hidden files
                if item.name.startswith("."):
                    continue
                    
                rel_path = item.relative_to(self.root)
                
                # Apply campaign filter if at top level
                if campaign_filter and str(rel_path).startswith("campaigns/"):
                    parts = rel_path.parts
                    if len(parts) >= 2 and parts[1] != campaign_filter:
                        continue

                is_compliant = self.schema.is_compliant(str(rel_path))
                
                status = AuditStatus.VALID if is_compliant else AuditStatus.ORPHAN
                msg = None if is_compliant else f"Not in schema: {self.schema.get_template_for(str(rel_path))}"
                
                node = AuditNode(
                    name=item.name,
                    path=item,
                    is_dir=item.is_dir(),
                    status=status,
                    message=msg
                )
                
                # If it's a USV file and valid structurally, check row-level compliance
                if not item.is_dir() and item.suffix == ".usv" and is_compliant:
                    self._audit_usv_rows(item, node)

                parent_node.children.append(node)
                
                # Only recurse into valid directories or campaigns
                # (We don't want to crawl massive orphan directories)
                if item.is_dir() and (is_compliant or item.name == "campaigns"):
                    # Limit depth for very large collections to keep report usable
                    if "companies" not in rel_path.parts:
                        self._recursive_audit(item, node, campaign_filter)
                        
        except Exception as e:
            parent_node.children.append(AuditNode(
                name="ERROR", path=current_path, is_dir=False, 
                status=AuditStatus.ERROR, message=str(e)
            ))

    def _audit_usv_rows(self, usv_path: Path, node: AuditNode) -> None:
        """Checks if USV rows match expected column count from nearest datapackage.json."""
        # Find nearest datapackage.json
        dp_path = usv_path.parent / "datapackage.json"
        if not dp_path.exists():
            # Try one level up (common for sharded files)
            dp_path = usv_path.parent.parent / "datapackage.json"
            
        if not dp_path.exists():
            return

        try:
            with open(dp_path, "r") as f:
                dp_data = json.load(f)
                # Find the resource matching this file path or the generic one
                expected_cols = len(dp_data["resources"][0]["schema"]["fields"])
                
            total_rows = 0
            non_conforming = 0
            
            with open(usv_path, "r", encoding="utf-8") as f:
                for line in f:
                    total_rows += 1
                    clean_line = line.strip("\x1e\n")
                    if not clean_line:
                        continue
                    parts = clean_line.split(UNIT_SEP)
                    if len(parts) != expected_cols:
                        non_conforming += 1
            
            if non_conforming > 0:
                node.status = AuditStatus.NON_CONFORMING
                node.message = f"{non_conforming}/{total_rows} rows have invalid column count (Expected {expected_cols})"
                node.stats = {"total_rows": total_rows, "invalid_rows": non_conforming}
        except Exception as e:
            logger.debug(f"Failed to audit USV rows for {usv_path}: {e}")

    def get_orphans(self, node: AuditNode) -> List[Path]:
        """Recursively collects paths of all items marked as ORPHAN."""
        orphans = []
        for child in node.children:
            if child.status == AuditStatus.ORPHAN:
                orphans.append(child.path)
            # Recurse into valid directories to find nested orphans
            # but don't recurse into orphans themselves
            elif child.is_dir:
                orphans.extend(self.get_orphans(child))
        return orphans

    def generate_removal_report(self, orphans: List[Path], output_path: Path) -> None:
        """
        Generates a text file containing absolute local paths of orphans.
        This report can be fed into scripts/execute_cleanup.py for distributed removal.
        """
        with open(output_path, "w", encoding="utf-8") as f:
            for p in orphans:
                f.write(f"{p.absolute()}\n")

def dump_audit_tree(node: AuditNode, console: Optional[Any] = None, tree: Optional[Any] = None) -> Any:
    """Renders the audit tree using Rich's Tree widget."""
    from rich.tree import Tree
    from rich.text import Text
    
    colors = {
        AuditStatus.VALID: "green",
        AuditStatus.MISSING: "red",
        AuditStatus.ORPHAN: "yellow",
        AuditStatus.ERROR: "bold red",
        AuditStatus.NON_CONFORMING: "magenta"
    }
    
    status_color = colors.get(node.status, "white")
    status_text = Text(f"[{node.status:14}] ", style=status_color)
    name_text = Text(node.name)
    if node.message:
        name_text.append(f" ({node.message})", style="italic dim")
    
    label = Text.assemble(status_text, name_text)
    
    if tree is None:
        tree = Tree(label)
    else:
        # Only add children that are NOT valid to keep the report focused
        # unless it's a top-level container
        if node.status != AuditStatus.VALID or not node.children:
             tree = tree.add(label)
        else:
             # If valid, just add it but we might skip its valid children later
             tree = tree.add(label)
        
    for child in node.children:
        # Optimization: Only show non-valid items in the tree to reduce noise
        if child.status != AuditStatus.VALID:
            dump_audit_tree(child, tree=tree)
        elif child.is_dir and any(c.status != AuditStatus.VALID for c in child.children):
            # Show valid dir if it contains invalid items
            dump_audit_tree(child, tree=tree)
            
    return tree
